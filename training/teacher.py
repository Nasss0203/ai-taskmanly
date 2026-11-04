"""Teacher answers for fine-tuning (kế hoạch train Colab, T2, T3).

Runs the real ``ModificationPlannerService`` on each synthetic request with a
bigger model behind Ollama (on Colab: ``qwen3:14b``). Every model call the
planner makes is recorded with its exact system prompt, user prompt and JSON
answer. The raw labels must pass schema, semantics and expectations BEFORE
application normalisation; the finished plan must pass as well.

The output is chat data for the student: one line per model call.

    python -m training.teacher --model qwen3:14b \
        --requests training/data/requests.jsonl --output training/data/sft.jsonl
"""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from app.llm.base import LLMGenerationResult, LLMProvider
from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from app.modules.modification_planner.validators.modification_planner_semantic_validator import (
    validate_modification_plan_semantics,
)
from scripts.evaluate_generation import _text, check_plan

# Two calls per drafted plan: the route, then the operations (no retries).
MODEL_CALLS_PER_PLAN = 2
FILTER_VERSION = "raw-labels-v1"


class RecordingProvider:
    """Passes calls to the teacher and keeps what was asked and answered."""

    def __init__(self, inner: LLMProvider) -> None:
        self.inner = inner
        self.provider_name = inner.provider_name
        self.model_name = inner.model_name
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        result = await self.inner.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_new_tokens=max_new_tokens,
            response_schema=response_schema,
        )
        self.calls.append({"system": system_prompt, "user": user_prompt, "assistant": result.text})
        return result

    async def close(self) -> None:
        await self.inner.close()


def extra_failures(plan: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    """Checks check_plan has no key for: sourced items and a minimum count."""
    todos = [_text(b["content"]["text"]) for op in plan.get("operations", []) if op.get("type") == "INSERT_BLOCKS"
             for b in op.get("blocks", []) if b.get("type") == "TODO"]
    failed = []
    if "todos_from" in expect:
        allowed = [_text(text) for text in expect["todos_from"]]
        if any(not any(todo in source or source in todo for source in allowed) for todo in todos):
            failed.append("todos_from")
    if expect.get("min_todos", 0) > len(todos):
        failed.append("min_todos")
    return failed


class _RawLabelRejected(Exception):
    """Bypass the app's ValueError handling and preserve the training reason."""


class _RawLabelPlanner(ModificationPlannerService):
    """Training-only gate; application code and saved answers stay unchanged."""

    def __init__(self, provider: LLMProvider, example: dict[str, Any]) -> None:
        super().__init__(provider)
        self._example = example

    def _build_plan_from_stage_two(self, request, route, generation):
        plan = super()._build_plan_from_stage_two(request, route, generation)
        # This hook runs before reanchoring, checklist conversion or grounding.
        try:
            validate_modification_plan_semantics(plan, request.context)
        except ValueError as exc:
            raise _RawLabelRejected("raw_semantics") from exc
        raw = plan.model_dump(mode="json")
        failures = check_plan(raw, self._example["expect"], self._example["request"]["context"])
        failures += extra_failures(raw, self._example["expect"])
        if failures:
            raise _RawLabelRejected(",".join("raw_" + name for name in failures))
        return plan


async def answer(example: dict[str, Any], provider: LLMProvider) -> dict[str, Any]:
    """The kept chat examples of one request, or why it was dropped."""
    recorder = RecordingProvider(provider)
    started = perf_counter()
    try:
        request = ModificationPlannerRequest.model_validate(example["request"])
        response = await _RawLabelPlanner(recorder, example).process(request)
    except _RawLabelRejected as exc:
        return {"id": example["id"], "kept": False, "reason": str(exc),
                "seconds": round(perf_counter() - started, 1)}
    except Exception as exc:  # Invalid JSON / schema / plan: the teacher was wrong.
        return {"id": example["id"], "kept": False, "reason": type(exc).__name__,
                "seconds": round(perf_counter() - started, 1)}
    plan = response.result.model_dump(mode="json")
    failed = check_plan(plan, example["expect"], example["request"]["context"]) + extra_failures(
        plan, example["expect"])
    if len(recorder.calls) != MODEL_CALLS_PER_PLAN:
        failed.append("model_calls")
    seconds = round(perf_counter() - started, 1)
    if failed:
        return {"id": example["id"], "kept": False, "reason": ",".join(failed), "seconds": seconds}
    return {
        "id": example["id"], "kept": True, "seconds": seconds,
        "chats": [{
            "id": f"{example['id']}-{index}", "kind": example["kind"], "lang": example["lang"],
            "messages": [
                {"role": "system", "content": call["system"]},
                {"role": "user", "content": call["user"]},
                {"role": "assistant", "content": call["assistant"]},
            ],
        } for index, call in enumerate(recorder.calls)],
    }


async def run(requests: Path, output: Path, provider: LLMProvider, limit: int | None) -> dict[str, Any]:
    examples = [json.loads(line) for line in requests.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Colab sessions end: the log says which requests are done, so a rerun carries on.
    log_path = output.with_suffix(".log.jsonl")
    logged = ([json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
              if log_path.exists() else [])
    if any(entry.get("filter_version") != FILTER_VERSION for entry in logged):
        raise ValueError("Existing log has a different filter version; use a new output path.")
    if output.exists() and output.stat().st_size and not logged:
        raise ValueError("Existing dataset without a matching log; use a new output path.")
    if any(entry.get("kept") for entry in logged) and not output.exists():
        raise ValueError("Kept records are missing; use a new output path.")
    done = {entry["id"] for entry in logged}
    todo = [e for e in examples if e["id"] not in done][:limit]
    output.parent.mkdir(parents=True, exist_ok=True)
    kept = dropped = 0
    reasons: dict[str, int] = {}
    with output.open("a", encoding="utf-8") as chats, log_path.open("a", encoding="utf-8") as log:
        for example in todo:
            result = await answer(example, provider)
            result["filter_version"] = FILTER_VERSION
            for chat in result.pop("chats", []):
                chats.write(json.dumps(chat, ensure_ascii=False) + "\n")
            log.write(json.dumps(result, ensure_ascii=False) + "\n")
            chats.flush()
            log.flush()
            if result["kept"]:
                kept += 1
            else:
                dropped += 1
                reasons[result["reason"]] = reasons.get(result["reason"], 0) + 1
    return {"answered": len(todo), "kept": kept, "dropped": dropped, "reasons": reasons,
            "alreadyDone": len(done)}


async def main(args: argparse.Namespace) -> None:
    # No app Settings: Colab has no .env and needs no service token.
    from app.llm.providers.ollama import OllamaProvider

    provider = OllamaProvider(
        base_url=args.ollama_url, model_name=args.model,
        timeout_seconds=args.timeout, num_ctx=args.num_ctx,
    )
    try:
        summary = await run(args.requests, args.output, provider, args.limit)
    finally:
        await provider.close()
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--requests", type=Path, default=Path("training/data/requests.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("training/data/sft.jsonl"))
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--limit", type=int)
    asyncio.run(main(parser.parse_args()))
