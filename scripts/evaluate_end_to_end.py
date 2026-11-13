"""Run sentences through the AI service and NestJS's checks, end to end (prompt 2026-11-10/05).

Each sentence goes: intent → page intent → NestJS's
``AiPageInstructionPlannerService`` through ``be-task-management/scripts/
ai-admission-probe.ts`` (no database, no network) → planner, only for what
NestJS let through (rules first, the model when they do not answer, as in the
app) → NestJS's check of the draft. The report says where each
sentence stops and whether that is what the case expects. An ACTIVITY Page is
taken as already picked by the user. Read-only.

Run: ``python -m scripts.evaluate_end_to_end --cases evaluation/simulated_user_english.jsonl
--be ../be-task-management [--output report.json]``
"""

import argparse
import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Callable

from scripts.evaluate_generation import CONTEXTS
from scripts.evaluate_simulated_users import check

CURRENT_PAGE_ID = "00000000-0000-4000-8000-000000000001"
MODEL_PROVIDER = "ollama"


def check_draft(plan: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    wanted = expect["op"]
    if isinstance(wanted, str):
        return check(plan, expect)
    got = {operation["type"] for operation in plan.get("operations") or []}
    failed = [] if got == set(wanted) else ["op=" + ",".join(sorted(got))]
    return failed + [name for name in check(plan, {**expect, "op": next(iter(got), "")}) if not name.startswith("op=")]


def run_probe(be: Path, items: list[dict[str, Any]], quiet: bool = False) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as folder:
        source, target = Path(folder) / "in.json", Path(folder) / "out.json"
        source.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        npx = shutil.which("npx") or "npx"
        subprocess.run([npx, "ts-node", "-T", "-r", "tsconfig-paths/register", "scripts/ai-admission-probe.ts",
                        str(source), str(target)], cwd=be, check=True, capture_output=quiet)
        return json.loads(target.read_text(encoding="utf-8"))


def error_stop(error: Exception) -> str:
    from app.core.exceptions import DraftNotDoneError, LLMProviderError, LLMUnavailableError, WritingNotDoneError

    if isinstance(error, (WritingNotDoneError, DraftNotDoneError)):
        return f"not-done:{type(error).__name__}"
    if isinstance(error, LLMProviderError) and not isinstance(error, LLMUnavailableError):
        return f"system:{type(error).__name__}"
    raise error


def stop_point(row: dict[str, Any]) -> str:
    if row.get("error"):
        return row["error"]
    if row.get("wrongPage"):
        return "wrong-page"
    if row["intent"] != "MODIFY_PAGE":
        return f"intent:{row['intent']}"
    nest = row.get("nestjs") or {}
    if nest.get("stage") == "refused":
        return f"nestjs:{nest.get('status')}"
    if nest.get("stage") == "clarify":
        return f"nestjs-ask:{nest.get('reason') or nest.get('status')}"
    if nest.get("stage") != "admitted":
        return f"nestjs-error:{nest.get('status')}"
    if row.get("planStatus") == "NEED_MORE_CONTEXT":
        return "planner-ask"
    return "draft"


def verdict(row: dict[str, Any], expect: dict[str, Any]) -> bool:
    stop = row["stop"]
    if expect.get("refuse"):
        return stop.startswith(("intent:OTHER", "intent:UNCLEAR", "nestjs:"))
    if expect.get("ask"):
        return stop == "planner-ask" or stop.startswith(("nestjs-ask:", "intent:UNCLEAR"))
    return stop == "draft" and not row["failed"]


async def run_cases(cases: list[dict[str, Any]], services: Any, probe: Callable[[list[dict[str, Any]]], dict[str, Any]],
                    contexts: dict[str, Any], pages: list[dict[str, str]] | None = None,
                    current_page_id: str = CURRENT_PAGE_ID,
                    titles: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    from app.modules.intent.schemas.intent_schema import IntentRequest
    from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
    from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest

    by_id = {case["id"]: case for case in cases}
    named = titles([{"id": case["id"], "kind": "titles", "instruction": case["instruction"],
                     "pages": pages or [{"id": case["id"], "title": contexts[case["page"]]["page"]["title"]}]}
                    for case in cases]) if titles and cases else {}
    rows, first_items = [], []
    for case in cases:
        current = current_page_id if case.get("current") else None
        found = (named.get(case["id"]) or {}).get("titles") or []
        row: dict[str, Any] = {"id": case["id"], "instruction": case["instruction"], "failed": [], "usedModel": False}
        started = perf_counter()
        try:
            intent = await services.intents.process(IntentRequest(instruction=case["instruction"], currentPageId=current,
                                                                  pageTitles=found))
            row["intent"] = intent.result.intent
            row["usedModel"] = intent.provider == MODEL_PROVIDER
            if row["intent"] == "MODIFY_PAGE":
                page = await services.pages.process(PageIntentRequest(instruction=case["instruction"], currentPageId=current,
                                                                      pageTitles=found))
                page_intent = page.result.model_dump(mode="json")
                row.update(reference=page_intent.get("referenceType"), pageIntentModel=page.model, pageIntent=page_intent)
                row["usedModel"] = row["usedModel"] or page.provider == MODEL_PROVIDER
                first_items.append({"id": case["id"], "instruction": case["instruction"],
                                    "pageTitle": contexts[case["page"]]["page"]["title"], "pageIntent": page_intent,
                                    **({"pages": pages} if pages else {}),
                                    **({"currentPageId": current} if current else {})})
        except Exception as exc:
            row["error"] = error_stop(exc)
            row.setdefault("intent", None)
        row["seconds"] = round(perf_counter() - started, 2)
        rows.append(row)

    admission = probe(first_items) if first_items else {}
    items_by_id = {item["id"]: item for item in first_items}
    second_items = []
    for row in rows:
        row["nestjs"] = admission.get(row["id"])
        nest = row["nestjs"] or {}
        row["pageTitle"] = nest.get("pageTitle")
        case = by_id[row["id"]]
        if nest.get("stage") != "admitted" or row.get("error"):
            continue
        if pages and nest.get("pageTitle") != contexts[case["page"]]["page"]["title"]:
            row["wrongPage"] = True
            continue
        if not row["pageIntent"].get("instruction"):
            continue
        started = perf_counter()
        try:
            response = await services.planner.process(ModificationPlannerRequest(
                instruction=row["pageIntent"]["instruction"], context=contexts[case["page"]]))
            plan = response.result.model_dump(mode="json")
            row.update(plan=plan, planStatus=plan.get("status"), plannerModel=response.model)
            row["usedModel"] = row["usedModel"] or response.provider == MODEL_PROVIDER
            second_items.append({**items_by_id[row["id"]], "plan": plan})
        except Exception as exc:
            row["error"] = error_stop(exc)
        row["seconds"] = round(row["seconds"] + perf_counter() - started, 2)

    checked = probe(second_items) if second_items else {}
    for row in rows:
        if row["id"] in checked:
            row["nestjs"] = checked[row["id"]]
        row.pop("pageIntent", None)
        row["stop"] = stop_point(row)
        expect = by_id[row["id"]]["expect"]
        if row["stop"] == "draft" and "op" in expect:
            row["failed"] = check_draft(row["plan"], expect)
    return rows


def build_services(config: Any) -> Any:
    from app.llm.providers.ollama import OllamaProvider
    from app.modules.intent.services.intent_service import IntentService
    from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
    from app.modules.page_intent.services.page_intent_service import PageIntentService

    def provider(model: str | None) -> OllamaProvider:
        name = model or config.ollama_model
        return OllamaProvider(base_url=config.ollama_base_url, model_name=name,
                              timeout_seconds=config.ollama_timeout_seconds, num_ctx=config.ollama_num_ctx,
                              num_gpu=config.ollama_model_num_gpu.get(name, config.ollama_num_gpu))

    intent_provider = provider(config.ollama_intent_model)
    planner_provider = provider(config.ollama_modification_planner_model)
    return SimpleNamespace(intents=IntentService(intent_provider), pages=PageIntentService(intent_provider),
                           planner=ModificationPlannerService(planner_provider), provider=provider,
                           providers=[intent_provider, planner_provider])


async def close_services(services: Any) -> None:
    for provider in services.providers:
        await provider.close()


async def main(args: argparse.Namespace) -> int:
    from app.core.config import get_settings

    services = build_services(get_settings())
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {case["id"]: case for case in cases}
    try:
        rows = await run_cases(cases, services, lambda items: run_probe(args.be, items), CONTEXTS,
                               titles=lambda items: run_probe(args.be, items))
    finally:
        await close_services(services)

    for row in rows:
        expect = by_id[row["id"]]["expect"]
        row["ok"] = verdict(row, expect)
        want = "refuse" if expect.get("refuse") else "ask" if expect.get("ask") else "draft"
        print(f"{row['id']}: {'OK ' if row['ok'] else 'BAD'} want={want:6} stop={row['stop']:32} "
              f"ref={row.get('reference')} failed={row['failed']} ({row['seconds']}s) | {row['instruction']}",
              flush=True)
    summary = {"cases": len(rows), "ok": sum(row["ok"] for row in rows),
               "stops": {stop: sum(row["stop"] == stop for row in rows) for stop in sorted({r["stop"] for r in rows})}}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output:
        for row in rows:
            if row["ok"]:
                row.pop("plan", None)
        args.output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--be", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
