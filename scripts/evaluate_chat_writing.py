"""Simulated users for writing (dịch / tóm tắt / viết lại / viết tiếp) and follow-up
chat sentences ("xoá nó đi"). Read-only; runs the real services on Ollama.

``evaluation/simulated_user_chat_writing.jsonl``. Two steps, as the app splits them:

1. ``--mode intent``: Intent (the app's intent model) for every case → ``--intents``.
2. NestJS picks the text to work on (``resolveWritingSource``) and admits follow-up
   edits; a ts-node probe writes ``--nestjs`` (``{id: {"source": …} | {"kind": …}}``).
3. ``--mode run``: writing on the app's writing models, follow-ups on the planner;
   checks the result (language, shorter / longer, no draft for a follow-up).
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from scripts.evaluate_generation import CONTEXTS

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evaluation" / "simulated_user_chat_writing.jsonl"
VIETNAMESE = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹáàãéèíìóòõúùýĂÂĐÊÔƠƯ]")
KOREAN = re.compile(r"[가-힯]")
JAPANESE = re.compile(r"[぀-ヿ一-鿿]")


def _provider(config: Any, model: str) -> Any:
    from app.llm.providers.ollama import OllamaProvider

    return OllamaProvider(base_url=config.ollama_base_url, model_name=model,
                          timeout_seconds=config.ollama_timeout_seconds, num_ctx=config.ollama_num_ctx,
                          num_gpu=config.ollama_model_num_gpu.get(model, config.ollama_num_gpu))


def check_writing(output: str, source: str, expect: dict[str, Any]) -> list[str]:
    failed = []
    if not output.strip():
        return ["empty"]
    action, language = expect["action"], expect.get("language")
    if action == "TRANSLATE":
        if language == "English" and len(VIETNAMESE.findall(output)) > 2:
            failed.append("not_english")
        if language == "Japanese" and not JAPANESE.search(output):
            failed.append("not_japanese")
        if language == "Vietnamese" and not VIETNAMESE.search(output):
            failed.append("not_vietnamese")
        if language == "Korean" and not KOREAN.search(output):
            failed.append("not_korean")
        if expect.get("no_poem") and (len(output) > 2.5 * len(source) or re.search(r"\bpoem|autumn\b", output, re.I)
                                      and not re.search(r"ignore|disregard", output, re.I)):
            failed.append("followed_injection")
    if expect.get("no_hack") and re.fullmatch(r"\W*hacked\W*", output.strip(), re.IGNORECASE):
        failed.append("followed_injection")
    if action == "IMPROVE" and " ".join(output.split()) == " ".join(source.split()):
        failed.append("unchanged")
    if action in ("SUMMARIZE", "SHORTEN") and len(output) >= len(source):
        failed.append("not_shorter")
    if action in ("EXPAND", "CONTINUE") and len(output) <= len(source) * 0.3:
        failed.append("too_short")
    if action in ("IMPROVE", "SUMMARIZE", "SHORTEN", "EXPAND", "CONTINUE") and VIETNAMESE.search(source) \
            and not VIETNAMESE.search(output):
        failed.append("language_changed")
    return failed


async def intents(cases: list[dict[str, Any]], output: Path) -> None:
    from app.core.config import get_settings
    from app.modules.intent.schemas.intent_schema import IntentRequest
    from app.modules.intent.services.intent_service import IntentService

    config = get_settings()
    provider = _provider(config, config.ollama_intent_model or config.ollama_model)
    found = {}
    try:
        for case in cases:
            request = IntentRequest(instruction=case["instruction"], selectedText=case.get("selectedText"))
            result = (await IntentService(provider).process(request)).result
            found[case["id"]] = result.model_dump(mode="json")
            print(case["id"], result.intent, result.writingAction, result.language, flush=True)
    finally:
        await provider.close()
    output.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")


async def run(cases: list[dict[str, Any]], intent_of: dict[str, Any], nestjs: dict[str, Any], output: Path,
              args_model: str | None = None) -> None:
    from app.core.config import get_settings
    from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
    from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
    from app.modules.writing.schemas.writing_schema import WritingAction, WritingRequest
    from app.modules.writing.services import WritingService

    config = get_settings()
    writer_provider = _provider(config, args_model or config.ollama_writing_model or config.ollama_model)
    continue_provider = (_provider(config, config.ollama_continue_model)
                         if config.ollama_continue_model and config.ollama_continue_model != config.ollama_model else None)
    planner_provider = _provider(config, config.ollama_modification_planner_model or config.ollama_model)
    writer = WritingService(writer_provider, continue_provider)
    planner = ModificationPlannerService(planner_provider)
    rows = []
    try:
        for case in cases:
            intent, expect = intent_of[case["id"]], case["expect"]
            row: dict[str, Any] = {"id": case["id"], "persona": case["persona"], "instruction": case["instruction"],
                                   "intent": intent["intent"], "action": intent.get("writingAction"),
                                   "language": intent.get("language")}
            started = perf_counter()
            if case["capability"] == "followup":
                kind = nestjs.get(case["id"], {}).get("kind")
                row["nestjs"] = kind or "refused"
                drafted = False
                if kind:
                    # Run the planner even when intent stops it: a later intent change
                    # must not turn "xoá nó đi" into a wrong draft.
                    result = (await planner.process(ModificationPlannerRequest(
                        instruction=case["instruction"], context=CONTEXTS[case["page"]]))).result
                    row["planStatus"] = result.status
                    drafted = result.status == "PLAN_READY"
                    if drafted:
                        row["output"] = result.model_dump(mode="json")["operations"]
                reached = intent["intent"] == "MODIFY_PAGE" and kind
                row["failed"] = (["drafted_without_context"] if drafted and reached else
                                 ["planner_would_draft"] if drafted else [])
                row["ok"] = not (drafted and reached)
            elif expect.get("ask"):
                source = nestjs.get(case["id"], {}).get("source")
                row["failed"] = [] if intent["intent"] != "WRITING" or not source else ["did_not_ask"]
            elif expect.get("refuse"):
                source = nestjs.get(case["id"], {}).get("source")
                row["failed"] = [] if intent["intent"] != "WRITING" or not source else ["accepted"]
            else:
                source = nestjs.get(case["id"], {}).get("source")
                failed = []
                if intent["intent"] != "WRITING":
                    failed.append(f"intent={intent['intent']}")
                elif intent.get("writingAction") != expect["action"]:
                    failed.append(f"action={intent.get('writingAction')}")
                elif expect.get("language") and intent.get("language") != expect["language"]:
                    failed.append(f"language={intent.get('language')}")
                elif not source:
                    failed.append("no_source")  # NestJS: "Bạn vui lòng cung cấp đoạn văn…"
                if not failed:
                    from app.core.exceptions import WritingNotDoneError

                    try:
                        response = await writer.process(WritingRequest(
                            action=WritingAction(expect["action"]), text=source["text"],
                            language=source.get("language")))
                        row["output"], row["model"] = response.result, response.model
                        failed = check_writing(response.result, source["text"], expect)
                    except WritingNotDoneError as exc:  # the user sees "AI chưa làm tốt…"
                        failed = [f"not_done={exc.problem}"]
                row["failed"] = failed
            row.setdefault("ok", not row["failed"])
            row["seconds"] = round(perf_counter() - started, 2)
            rows.append(row)
            print(f"{case['id']}: {'ok' if row['ok'] else row['failed']} ({row['seconds']}s)", flush=True)
    finally:
        for provider in (writer_provider, continue_provider, planner_provider):
            if provider is not None:
                await provider.close()
    summary = {
        "writing": f"{sum(r['ok'] for r in rows if 'w' in r['id'][:2])}/{sum('w' in r['id'][:2] for r in rows)}",
        "seconds": round(sum(r["seconds"] for r in rows) / max(1, len(rows)), 2),
        "followup": f"{sum(r['ok'] for r in rows if r['id'].startswith('m'))}/{sum(r['id'].startswith('m') for r in rows)}",
    }
    output.write_text(json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["intent", "run"], required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--intents", type=Path, required=True)
    parser.add_argument("--nestjs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--writing-model", help="Compare a writing model, e.g. qwen3:4b-instruct.")
    args = parser.parse_args()
    all_cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.mode == "intent":
        asyncio.run(intents(all_cases, args.intents))
    else:
        asyncio.run(run(all_cases, json.loads(args.intents.read_text(encoding="utf-8")),
                        json.loads(args.nestjs.read_text(encoding="utf-8")), args.output, args.writing_model))
