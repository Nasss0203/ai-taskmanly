import argparse
import asyncio
import importlib
import json
import logging
import secrets
from collections import Counter
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.modules.modification_planner.services.sentence_text import text_key
from evaluation.natural_vi_generator import DEV_BANK, DEV_SEED, generate
from scripts import evaluate_page_question
from scripts.evaluate_chat_writing import check_writing
from scripts.evaluate_end_to_end import (
    build_services, close_services, error_stop, meter_snapshot, meter_usage, run_cases, run_probe, used_model,
)
from scripts.evaluate_generation import CONTEXTS, check_composition

OK, ASK, SYSTEM, DRAFT, PAGE = "dung", "hoi_lai", "loi_he_thong", "ban_nhap_sai", "sai_trang"
ORDER = [OK, ASK, SYSTEM, DRAFT, PAGE]
STOP_INTENTS = ("UNCLEAR", "OTHER")
ROOT = Path(__file__).resolve().parents[1]
SEED_FILE = ROOT / "evaluation" / "results" / "holdout_seed.txt"
HOLDOUT_MODULE = "evaluation.natural_vi_holdout_forms"
DEV2_MODULE = "evaluation.natural_vi_dev2_forms"
DEV2_SEED = 20261114
CAPABILITIES = ["modify", "compose", "writing", "question"]


def final_outcome(outcomes: list[str], must_stop: bool) -> str:
    worst = max(outcomes, key=ORDER.index)
    if PAGE in outcomes:
        return PAGE
    if must_stop:
        return DRAFT if DRAFT in outcomes else worst
    top, count = Counter(outcomes).most_common(1)[0]
    return top if count > len(outcomes) / 2 else worst


def modify_outcome(row: dict[str, Any], expect: dict[str, Any], title: str) -> str:
    stop = row["stop"]
    if stop.startswith(("system:", "nestjs-error:")):
        return SYSTEM
    if stop.startswith("not-done:"):
        return ASK
    asks = stop == "planner-ask" or stop.startswith("nestjs-ask:")
    stops_at_intent = stop in ("intent:UNCLEAR", "intent:OTHER")
    if expect.get("refuse"):
        if stops_at_intent or stop.startswith("nestjs:"):
            return OK
        return ASK if asks else DRAFT
    if expect.get("ask"):
        if asks or stop == "intent:UNCLEAR":
            return OK
        return ASK if stop == "intent:OTHER" or stop.startswith("nestjs:") else DRAFT
    if stop == "wrong-page" or (stop == "draft" and row.get("pageTitle") not in (None, title)):
        return PAGE
    if stop == "draft":
        return DRAFT if row["failed"] else OK
    if stops_at_intent or asks or stop.startswith("nestjs:"):
        return ASK
    return DRAFT


def _error_outcome(error: str) -> str:
    return SYSTEM if error.startswith("system:") else ASK


def writing_outcome(row: dict[str, Any], expect: dict[str, Any]) -> str:
    if row.get("error"):
        return _error_outcome(row["error"])
    if expect.get("ask"):
        return OK if row["intent"] != "WRITING" or not row.get("source") else DRAFT
    if row["intent"] in STOP_INTENTS:
        return ASK
    if row["intent"] != "WRITING" or row.get("action") != expect["action"]:
        return DRAFT
    if expect.get("language") and row.get("language") != expect["language"]:
        return DRAFT
    if row.get("source") is None:
        return ASK
    if text_key(row["source"]) != text_key(expect["source"]):
        return DRAFT
    return DRAFT if row["failed"] else OK


ERROR_KINDS = {"Writing result is empty.": "rong_sau_khi_cat", "Ollama response content is empty.": "model_tra_rong",
               "Ollama response does not contain message content.": "model_tra_sai"}


def writing_stage(row: dict[str, Any], expect: dict[str, Any]) -> str:
    if row.get("error"):
        return ":".join(part for part in (row.get("errorAt"), row["error"], row.get("errorKind")) if part)
    if expect.get("ask"):
        return "nhap_khi_phai_hoi" if row["intent"] == "WRITING" and row.get("source") else "dung"
    if row["intent"] != "WRITING":
        return f"intent:{row['intent']}"
    if row.get("action") != expect["action"]:
        return "sai_lenh"
    if expect.get("language") and row.get("language") != expect["language"]:
        return "sai_ngon_ngu"
    if row.get("source") is None:
        return "khong_lay_duoc_chu"
    if text_key(row["source"]) != text_key(expect["source"]):
        return "sai_chu"
    return "kiem_tra:" + ",".join(row["failed"]) if row["failed"] else "dung"


def extra_failures(draft: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    if "max_databases" in expect and len(draft.get("databases") or []) > expect["max_databases"]:
        return ["databases"]
    return []


def compose_stage(row: dict[str, Any], expect: dict[str, Any]) -> str:
    if row.get("error"):
        return row["error"]
    if expect.get("refuse"):
        return "nhap_khi_phai_chan" if row["intent"] == "CREATE_PAGE" else "dung"
    if row["intent"] != "CREATE_PAGE":
        return f"intent:{row['intent']}"
    return "kiem_tra:" + ",".join(row["failed"]) if row["failed"] else "dung"


def compose_outcome(row: dict[str, Any], expect: dict[str, Any]) -> str:
    if row.get("error"):
        return _error_outcome(row["error"])
    if expect.get("refuse"):
        return OK if row["intent"] != "CREATE_PAGE" else DRAFT
    if row["intent"] in STOP_INTENTS:
        return ASK
    if row["intent"] != "CREATE_PAGE":
        return DRAFT
    return DRAFT if row["failed"] else OK


def question_outcome(row: dict[str, Any], known_titles: set[str]) -> str:
    if row.get("error"):
        return _error_outcome(row["error"])
    failed = row["failed"]
    if not failed:
        return OK
    if any(name.startswith("page=") for name in failed):
        reference = (row.get("reference") or "").casefold()
        return PAGE if not reference or reference in known_titles else ASK
    if any(name.startswith("error=") for name in failed) or row["intent"] in STOP_INTENTS:
        return ASK
    return DRAFT


async def measure(cases: list[dict[str, Any]], once: Callable[[list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    runs = {row["id"]: [row] for row in await once(cases)}
    again = [case for case in cases if runs[case["id"]][0]["usedModel"]]
    for _ in range(2):
        if again:
            for row in await once(again):
                runs[row["id"]].append(row)
    results = []
    for case in cases:
        attempts = runs[case["id"]]
        outcomes = [attempt["outcome"] for attempt in attempts]
        expect = case["expect"]
        results.append({
            "id": case["id"], "group": case["group"], "instruction": case["instruction"],
            "outcome": final_outcome(outcomes, bool(expect.get("refuse") or expect.get("ask"))),
            "outcomes": outcomes, "stable": len(set(outcomes)) == 1, "allOk": all(o == OK for o in outcomes),
            "runs": len(outcomes), "attempts": attempts,
        })
    return results


def _count(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"cases": len(results)}
    for outcome in ORDER:
        counts[outcome] = sum(result["outcome"] == outcome for result in results)
    counts["allOk"] = sum(result["allOk"] for result in results)
    counts["unstable"] = sum(not result["stable"] for result in results)
    return counts


def _draft_source(row: dict[str, Any]) -> str:
    last = row["attempts"][-1]
    relaxed = last.get("relaxedOnly")
    return "|".join([row["group"], last.get("plannerModel") or "", ",".join(last.get("failed") or []),
                     "" if relaxed is None else str(relaxed)])


def summarize(results: dict[str, list[dict[str, Any]]], hide_sentences: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, rows in results.items():
        groups = {group: _count([row for row in rows if row["group"] == group]) for group in sorted({r["group"] for r in rows})}
        entry: dict[str, Any] = {"total": _count(rows), "groups": groups}
        stages: dict[str, Counter] = {}
        for row in rows:
            stage = row["attempts"][-1].get("stage")
            if stage and row["outcome"] != OK:
                stages.setdefault(row["group"], Counter())[stage] += 1
        if stages:
            entry["stages"] = {group: dict(counts) for group, counts in sorted(stages.items())}
        sources = Counter(_draft_source(row) for row in rows if row["outcome"] == DRAFT)
        if sources:
            entry["draftSources"] = dict(sorted(sources.items()))
        if not hide_sentences:
            entry["unstable"] = [row["id"] for row in rows if not row["stable"]]
            entry["problems"] = [{key: row[key] for key in ("id", "group", "outcome", "outcomes", "instruction")}
                                 | {"last": {k: v for k, v in row["attempts"][-1].items() if k in ("stop", "failed", "intent", "pageTitle")}}
                                 for row in rows if row["outcome"] != OK]
        summary[name] = entry
    return summary


def load_seed(path: Path) -> int:
    if path.exists():
        return int(path.read_text(encoding="utf-8").strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    seed = secrets.randbelow(2**31)
    path.write_text(f"{seed}\n", encoding="utf-8")
    return seed


def _sample_pages(data: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    titles = list(data["pages"].values()) + data["decoys"] + [data["open_page"]]
    pages = [{"id": f"00000000-0000-4000-8000-{index + 1:012d}", "title": title} for index, title in enumerate(titles)]
    return pages, pages[-1]["id"]


def _modify_once(data: dict[str, Any], services: Any, probe: Callable, contexts: dict[str, Any]) -> Callable:
    pages, open_id = _sample_pages(data)

    async def once(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {case["id"]: case for case in cases}
        rows = await run_cases(cases, services, probe, contexts, pages=pages, current_page_id=open_id, titles=probe)
        return [{"id": row["id"], "usedModel": row["usedModel"], "stop": row["stop"], "failed": row["failed"],
                 "intent": row.get("intent"), "pageTitle": row.get("pageTitle"), "stage": row["stop"],
                 "plannerModel": row.get("plannerModel"), "relaxedOnly": (row.get("nestjs") or {}).get("relaxedOnly"),
                 "outcome": modify_outcome(row, by_id[row["id"]]["expect"], contexts[by_id[row["id"]]["page"]]["page"]["title"])}
                for row in rows]

    return once


def _compose_once(services: Any, probe: Callable | None = None, pages: list[dict[str, str]] | None = None) -> Callable:
    from app.modules.intent.schemas.intent_schema import IntentRequest
    from app.modules.page_composition.schemas.page_composition_schema import PageCompositionRequest
    from app.modules.page_composition.services.page_composition_service import PageCompositionService

    composer = PageCompositionService(services.composer_provider)

    async def run(case: dict[str, Any], titles: list[str]) -> dict[str, Any]:
        expect = case["expect"]
        row: dict[str, Any] = {"id": case["id"], "usedModel": False, "failed": [], "intent": None}
        try:
            intent = await services.intents.process(IntentRequest(instruction=case["instruction"], pageTitles=titles))
            row.update(intent=intent.result.intent, usedModel=used_model(intent.provider))
            if row["intent"] == "CREATE_PAGE" and not expect.get("refuse"):
                response = await composer.process(PageCompositionRequest(instruction=case["instruction"]))
                row["usedModel"] = row["usedModel"] or used_model(response.provider)
                draft = response.result.model_dump(mode="json")
                row["failed"] = check_composition(draft, expect) + extra_failures(draft, expect)
                written = {text_key(block["content"].get("text", "")) for block in draft.get("blocks", [])
                           if isinstance(block.get("content"), dict)}
                if any(text_key(text) not in written for text in expect.get("texts", [])):
                    row["failed"].append("texts")
        except Exception as exc:
            row["error"] = error_stop(exc)
        row["outcome"] = compose_outcome(row, expect)
        row["stage"] = compose_stage(row, expect)
        return row

    async def once(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        named = probe([{"id": case["id"], "kind": "titles", "instruction": case["instruction"], "pages": pages}
                       for case in cases]) if probe and pages and cases else {}
        return [await run(case, (named.get(case["id"]) or {}).get("titles") or []) for case in cases]

    return once


def _writing_once(services: Any, probe: Callable) -> Callable:
    from app.modules.intent.schemas.intent_schema import IntentRequest
    from app.modules.writing.schemas.writing_schema import WritingAction, WritingRequest
    from app.modules.writing.services import WritingService

    writer = WritingService(services.writer_provider, services.continue_provider)

    async def once(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows, items, intents = [], [], {}
        for case in cases:
            row: dict[str, Any] = {"id": case["id"], "usedModel": False, "failed": [], "intent": None}
            try:
                response = await services.intents.process(IntentRequest(instruction=case["instruction"],
                                                                        selectedText=case.get("selectedText")))
                result = response.result
                row.update(intent=result.intent, action=result.writingAction, language=result.language,
                           usedModel=used_model(response.provider))
                if result.intent == "WRITING":
                    intents[case["id"]] = result
                    items.append({"id": case["id"], "kind": "writing", "instruction": case["instruction"],
                                  "selectedText": case.get("selectedText"), "intent": result.model_dump(mode="json")})
            except Exception as exc:
                row["error"] = error_stop(exc)
                row["errorAt"] = "intent"
            rows.append(row)
        sources = probe(items) if items else {}
        by_id = {case["id"]: case for case in cases}
        for row in rows:
            case = by_id[row["id"]]
            expect = case["expect"]
            found = (sources.get(row["id"]) or {}).get("source")
            row["source"] = found["text"] if found else None
            right = (row["id"] in intents and found and not expect.get("ask") and row["action"] == expect["action"]
                     and text_key(found["text"]) == text_key(expect["source"]))
            if right:
                try:
                    language = found.get("language") or row["language"]
                    written = await writer.process(WritingRequest(action=WritingAction(row["action"]), text=found["text"],
                                                                  language=language))
                    row["usedModel"] = row["usedModel"] or used_model(written.provider)
                    row["failed"] = check_writing(written.result, found["text"], expect)
                except Exception as exc:
                    row["usedModel"] = True
                    row["error"] = error_stop(exc)
                    row["errorAt"] = "viet"
                    row["errorKind"] = ERROR_KINDS.get(str(exc), "khac")
            row["outcome"] = writing_outcome(row, expect)
            row["stage"] = writing_stage(row, expect)
        return rows

    return once


def _question_once(data: dict[str, Any], services: Any, probe: Callable) -> Callable:
    from app.core.exceptions import WritingNotDoneError
    from app.modules.intent.schemas.intent_schema import IntentRequest
    from app.modules.page_question.schemas import PageQuestionRequest
    from app.modules.page_question.service import PageQuestionService

    questions = PageQuestionService(services.question_provider)
    known = {title.casefold() for title in [*data["pages"].values(), *data["decoys"]]}
    pages = [{"id": f"page-{index}", "title": title} for index, title in enumerate([*data["pages"].values(), *data["decoys"]])]

    async def run(case: dict[str, Any], titles: list[str]) -> dict[str, Any]:
        expect = case["expect"]
        row: dict[str, Any] = {"id": case["id"], "usedModel": False, "failed": [], "intent": None}
        try:
            response = await services.intents.process(IntentRequest(instruction=case["instruction"], pageTitles=titles))
            intent = response.result
            row.update(intent=intent.intent, reference=intent.pageReference, usedModel=used_model(response.provider))
            answer = problem = None
            if intent.intent == "PAGE_QUESTION" and "context" in expect:
                try:
                    answered = await questions.process(PageQuestionRequest(
                        question=case["instruction"], questionKind=intent.questionKind,
                        databaseReference=intent.databaseReference,
                        context=evaluate_page_question.CONTEXTS[expect["context"]]))
                    answer = answered.answer
                    row["usedModel"] = row["usedModel"] or answered.usedModel
                except WritingNotDoneError as exc:
                    problem = f"WRITING_NOT_DONE:{exc.problem}"
                    row["usedModel"] = True
            row["failed"] = evaluate_page_question._check(case, intent, answer, problem)
        except Exception as exc:
            row["error"] = error_stop(exc)
        row["outcome"] = question_outcome(row, known)
        return row

    async def once(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        named = probe([{"id": case["id"], "kind": "titles", "instruction": case["instruction"], "pages": pages}
                       for case in cases]) if cases else {}
        return [await run(case, (named.get(case["id"]) or {}).get("titles") or []) for case in cases]

    return once


def _print_report(summary: dict[str, Any], split: str) -> None:
    header = f"{'':26}{'câu':>5}{'đúng':>6}{'3/3':>5}{'hỏi lại':>9}{'lỗi HT':>8}{'nháp sai':>10}{'sai trang':>11}{'k.ổn định':>11}"
    print(f"\n=== {split} ===\n{header}")

    def line(label: str, counts: dict[str, int]) -> None:
        print(f"{label:26}{counts['cases']:>5}{counts[OK]:>6}{counts['allOk']:>5}{counts[ASK]:>9}{counts[SYSTEM]:>8}"
              f"{counts[DRAFT]:>10}{counts[PAGE]:>11}{counts['unstable']:>11}")

    for name, entry in summary.items():
        line(name.upper(), entry["total"])
        for group, counts in entry["groups"].items():
            line(f"  {group}", counts)
    for name, entry in summary.items():
        for used in entry.get("models", []):
            print(f"{name} [{','.join(used['tasks'])}] {used['provider']}:{used['model']} lượt gọi {used['calls']}, {used['secondsPerCall']} s/lượt, "
                  f"token vào {used['promptTokens']}, ra {used['completionTokens']}")
    for name, entry in summary.items():
        for group, counts in entry.get("stages", {}).items():
            print(f"{name} {group} dừng ở: " + ", ".join(f"{stage} {count}" for stage, count in sorted(counts.items())))
    for name, entry in summary.items():
        for problem in entry.get("problems", []):
            print(f"{problem['id']} {problem['outcome']} {problem['outcomes']} {problem['last']} | {problem['instruction']}")


def split_bank(split: str) -> tuple[dict[str, Any], int, bool]:
    if split == "holdout":
        return importlib.import_module(HOLDOUT_MODULE).BANK, load_seed(SEED_FILE), True
    if split == "dev2":
        return importlib.import_module(DEV2_MODULE).BANK, DEV2_SEED, False
    return DEV_BANK, DEV_SEED, False


async def run_split(args: argparse.Namespace) -> dict[str, Any]:
    from app.core.config import get_settings

    bank, seed, holdout = split_bank(args.split)
    wanted = args.only.split(",") if args.only else CAPABILITIES
    sets = generate(bank, seed)
    contexts = bank.get("contexts") or CONTEXTS
    if bank.get("question_contexts"):
        evaluate_page_question.CONTEXTS.update(bank["question_contexts"])
    config = get_settings()
    services = build_services(config, gemini_interval=args.gemini_interval)

    def probe(items: list[dict[str, Any]]) -> dict[str, Any]:
        return run_probe(args.be, items, quiet=holdout)

    makers = {"modify": lambda: _modify_once(bank["modify"], services, probe, contexts),
              "compose": lambda: _compose_once(services, probe, _sample_pages(bank["modify"])[0]),
              "writing": lambda: _writing_once(services, probe),
              "question": lambda: _question_once(bank["question"], services, probe)}
    results, usage = {}, {}
    try:
        for name in wanted:
            once = makers[name]()

            async def counted(cases: list[dict[str, Any]], capability: str = name, step: Callable = once) -> list[dict[str, Any]]:
                print(f"[{capability}] {len(cases)} câu", flush=True)
                return await step(cases)

            before = meter_snapshot(services)
            results[name] = await measure(sets[name], counted)
            usage[name] = meter_usage(services, before)
    finally:
        await close_services(services)
    summary = summarize(results, hide_sentences=holdout)
    for name, used in usage.items():
        summary[name]["models"] = used
    return {"split": args.split, **({"seed": seed} if not holdout else {}), "model": config.ollama_model,
            "providers": {task: f"{item.provider_name}:{item.model_name}" for task, item in services.meters.items()},
            "capabilities": summary}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "dev2", "holdout"], required=True)
    parser.add_argument("--be", type=Path, required=True)
    parser.add_argument("--only")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gemini-interval", type=float, default=0.0)
    args = parser.parse_args()
    if args.split == "holdout":
        logging.disable(logging.CRITICAL)
    try:
        report = asyncio.run(run_split(args))
    except Exception as exc:
        detail = "" if args.split == "holdout" else f": {exc}"
        print(f"Lần đo không hợp lệ, không có số nền ({type(exc).__name__}{detail})")
        return 2
    _print_report(report["capabilities"], args.split)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
