"""Run the simulated-user sentences through the real planner (kế hoạch thử như người dùng).

``evaluation/simulated_user_cases.jsonl`` holds sentences written in the voice
of five kinds of users (student, office worker, English, typing without marks,
someone trying to break it). Every sentence that should be drafted runs through
``ModificationPlannerService`` on Ollama, also the ones NestJS refuses today:
the report shows what the AI would do if they got through. Read-only.

Run: ``python -m scripts.evaluate_simulated_users [--admission admission.json]``
(``admission.json``: NestJS result per id, written by a ts-node probe).
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from app.modules.modification_planner.services.sentence_text import text_key
from scripts.evaluate_generation import CONTEXTS, check_composition

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evaluation" / "simulated_user_cases.jsonl"


def check(plan: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    """Names of the expectations the draft misses."""
    operations = plan.get("operations") or []
    if plan.get("status") != "PLAN_READY" or not operations:
        return [f"status={plan.get('status')}"]
    failed = []
    if {op["type"] for op in operations} != {expect["op"]}:
        failed.append("op=" + ",".join(sorted({op["type"] for op in operations})))
    if "blocks" in expect:
        got = {op.get("blockId") for op in operations}
        if got != set(expect["blocks"]):
            failed.append(f"blocks={sorted(b for b in got if b)}")
    if "checked" in expect and any(op.get("checked") != expect["checked"] for op in operations):
        failed.append("checked")
    if "texts" in expect:
        texts = []
        for op in operations:
            texts += [block["content"].get("text", "") for block in op.get("blocks") or []
                      if isinstance(block, dict) and isinstance(block.get("content"), dict)]
            if op["type"] == "SET_BLOCK_TEXT":
                texts.append(op.get("newText", ""))
        keys = {text_key(text) for text in texts}
        rows = text_key(json.dumps([op.get("rows") for op in operations], ensure_ascii=False))
        missing = [text for text in expect["texts"] if text_key(text) not in keys
                   and not re.search(rf"\b{re.escape(text_key(text))}\b", rows)]
        if missing:
            failed.append("texts")
    if "parent" in expect and any(op.get("parentBlockId") != expect["parent"] for op in operations
                                  if op["type"] == "INSERT_BLOCKS"):
        failed.append("parent")
    if "after" in expect and operations[0].get("afterBlockId") != expect["after"]:
        failed.append(f"after={operations[0].get('afterBlockId')}")
    return failed


async def run_composition(case: dict[str, Any], intents: Any, composer: Any) -> dict[str, Any]:
    """Create a Page: intent must be CREATE_PAGE, then the draft is checked."""
    from app.modules.intent.schemas.intent_schema import IntentRequest
    from app.modules.page_composition.schemas.page_composition_schema import PageCompositionRequest

    expect = case["expect"]
    started = perf_counter()
    intent = (await intents.process(IntentRequest(instruction=case["instruction"]))).result.intent
    row: dict[str, Any] = {"intent": intent, "want": "refuse" if expect.get("refuse") else "CREATE_PAGE"}
    if expect.get("refuse"):
        row.update(ok=intent != "CREATE_PAGE", aiOk=intent != "CREATE_PAGE",
                   failed=[] if intent != "CREATE_PAGE" else ["intent=CREATE_PAGE"])
        return row
    if intent != "CREATE_PAGE":
        row.update(ok=False, aiOk=False, failed=[f"intent={intent}"], seconds=round(perf_counter() - started, 2))
        return row
    try:
        response = await composer.process(PageCompositionRequest(instruction=case["instruction"]))
        draft = response.result.model_dump(mode="json")
        failed = check_composition(draft, expect)
        texts = {text_key(block["content"].get("text", "")) for block in draft.get("blocks", [])
                 if isinstance(block.get("content"), dict)}
        if any(text_key(text) not in texts for text in expect.get("texts", [])):
            failed.append("texts")
        row.update(model=response.model, failed=failed, ok=not failed, aiOk=not failed)
        if failed:
            row["output"] = {"title": draft["page"]["title"], "blocks": [
                (b.get("type"), (b.get("content") or {}).get("text")) for b in draft.get("blocks", [])],
                "databases": len(draft.get("databases", []))}
    except Exception as exc:  # what the user would see as an error
        row.update(ok=False, aiOk=False, failed=[f"error={type(exc).__name__}"])
    row["seconds"] = round(perf_counter() - started, 2)
    return row


async def main(args: argparse.Namespace) -> int:
    from app.core.config import get_settings
    from app.llm.providers.ollama import OllamaProvider
    from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
    from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService

    admission = json.loads(args.admission.read_text(encoding="utf-8")) if args.admission else {}
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    config = get_settings()
    provider = OllamaProvider(
        base_url=config.ollama_base_url,
        model_name=config.ollama_modification_planner_model or config.ollama_model,
        timeout_seconds=config.ollama_timeout_seconds, num_ctx=config.ollama_num_ctx,
        # As app/main.py: one placement per model (OLLAMA_MODEL_NUM_GPU).
        num_gpu=config.ollama_model_num_gpu.get(
            config.ollama_modification_planner_model or config.ollama_model,
            config.ollama_modification_planner_num_gpu or config.ollama_num_gpu),
    )
    service = ModificationPlannerService(provider)
    from app.modules.intent.services.intent_service import IntentService
    from app.modules.page_composition.services.page_composition_service import PageCompositionService

    intent_provider = OllamaProvider(
        base_url=config.ollama_base_url, model_name=config.ollama_intent_model or config.ollama_model,
        timeout_seconds=config.ollama_timeout_seconds, num_ctx=config.ollama_num_ctx,
        num_gpu=config.ollama_model_num_gpu.get(config.ollama_intent_model or config.ollama_model,
                                                config.ollama_num_gpu),
    )
    intents, composer = IntentService(intent_provider), PageCompositionService(provider)
    results = []
    try:
        for case in cases:
            nest = admission.get(case["id"], {})
            row = {"id": case["id"], "persona": case["persona"], "instruction": case["instruction"],
                   "nestjs": nest.get("kind") or ("refused" if nest else None),
                   "nestjsWhy": (nest.get("why") or {}).get("kind") if nest else None}
            if case.get("capability") == "composition":
                row.update(await run_composition(case, intents, composer))
                results.append(row)
                print(f"{case['id']}: intent={row['intent']} ai={'ok' if row['ok'] else row['failed']} "
                      f"({row.get('seconds')}s, {row.get('model')})", flush=True)
                continue
            if case["expect"].get("refuse"):
                row["want"] = "refuse"
                row["ok"] = bool(nest) and not nest.get("kind")
                results.append(row)
                print(f"{case['id']}: refuse -> nestjs={row['nestjs']}", flush=True)
                continue
            if case["expect"].get("ask"):
                # Unsure on purpose ("xoá 3 việc A, B"): asked back or refused, never drafted.
                row["want"] = "ask"
                response = await service.process(ModificationPlannerRequest(
                    instruction=case["instruction"], context=CONTEXTS[case["page"]]))
                row["model"] = response.model
                row["aiOk"] = response.result.status == "NEED_MORE_CONTEXT"
                row["failed"] = [] if row["aiOk"] else [f"status={response.result.status}"]
                row["ok"] = row["aiOk"] or row["nestjs"] == "refused"
                results.append(row)
                print(f"{case['id']}: ask -> nestjs={row['nestjs']} ai={response.result.status}", flush=True)
                continue
            row["want"] = case["expect"]["op"]
            started = perf_counter()
            try:
                response = await service.process(ModificationPlannerRequest(
                    instruction=case["instruction"], context=CONTEXTS[case["page"]]))
                plan = response.result.model_dump(mode="json")
                row["model"] = response.model
                row["failed"] = check(plan, case["expect"])
                if row["failed"]:
                    row["output"] = plan
            except Exception as exc:  # what the user would see as an error
                row["failed"] = [f"error={type(exc).__name__}"]
            row["seconds"] = round(perf_counter() - started, 2)
            row["aiOk"] = not row["failed"]
            row["ok"] = row["aiOk"] and bool(row["nestjs"]) and row["nestjs"] != "refused"
            results.append(row)
            print(f"{case['id']}: nestjs={row['nestjs']} ai={'ok' if row['aiOk'] else row['failed']} "
                  f"({row['seconds']}s, {row.get('model')})", flush=True)
    finally:
        await provider.close()
        await intent_provider.close()
    drafted = [r for r in results if r["want"] != "refuse"]
    summary = {
        "cases": len(results),
        "endToEndOk": sum(r["ok"] for r in results),
        "refusedCorrectly": sum(r["ok"] for r in results if r["want"] == "refuse"),
        "refuseCases": sum(r["want"] == "refuse" for r in results),
        "nestjsWronglyRefused": sum(r["nestjs"] in (None, "refused") for r in drafted) if admission else None,
        "aiOk": sum(r["aiOk"] for r in drafted),
        "draftCases": len(drafted),
        "byRules": sum(r.get("model") in ("rules",) or str(r.get("model", "")).endswith("-v1") for r in drafted),
    }
    if args.output:
        args.output.write_text(json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--output", type=Path)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
