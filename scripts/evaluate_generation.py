"""Measure page composition and modification planning on a real model.

Read-only: no database access, nothing is applied. Each case runs the real
service (prompt, structured output, validation, normalisation) ``--repeat``
times and is checked against the expectations in the case file.

Run with ``python -m scripts.evaluate_generation`` (uses .env settings), or
compare models, e.g. ``--model qwen3:8b`` or ``--planner-model qwen3:8b``.
"""

import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from app.shared.list_markers import strip_list_marker


DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evaluation" / "generation_cases.jsonl"


def _text(value: str) -> str:
    return strip_list_marker(value).strip().rstrip(".!").casefold()


def _block(ref: str, kind: str, text: str, order: int) -> dict[str, Any]:
    return {
        "id": ref, "parentBlockId": None, "type": kind, "orderIndex": order, "title": None,
        "content": {"text": text}, "styleConfig": {"level": 1} if kind == "HEADER" else None,
        "dataConfig": None,
    }


def _context(title: str, blocks: list[dict[str, Any]], databases: list[dict[str, Any]],
             references: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": 1, "builtAt": "2026-10-26T00:00:00.000Z",
        "page": {"id": "page-1", "workspaceId": "workspace-1", "teamspaceId": None, "parentPageId": None,
                 "title": title, "icon": None, "coverUrl": None, "updatedAt": "2026-10-26T00:00:00.000Z"},
        "blocks": blocks, "databaseReferences": references, "databases": databases,
        "completeness": {
            "blocks": {"total": len(blocks), "included": len(blocks), "truncated": False},
            "databases": {"total": len(databases), "included": len(databases), "truncated": False},
            "rows": [{"databaseId": db["id"], "total": len(db["rows"]), "included": len(db["rows"]),
                      "truncated": False, "selection": "BOUNDED"} for db in databases],
            "textTruncated": False,
        },
    }


def _todo(ref: str, text: str, checked: bool, order: int) -> dict[str, Any]:
    return {**_block(ref, "TODO", text, order), "content": {"text": text, "checked": checked}}


def _property(ref: str, name: str, kind: str, position: str, options: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": ref, "name": name, "type": kind, "position": position, "isDefault": kind == "TITLE",
            "isHideable": kind != "TITLE", "options": options or []}


# The "Hội họp tuần" page a real user tested, and a release page with a database.
CONTEXTS: dict[str, dict[str, Any]] = {
    "meeting": _context("Hội họp tuần", [
        _block("b0", "HEADER", "Tuần họp", 0),
        _block("b1", "TEXT", "Các nhiệm vụ cần thực hiện trong tuần này:", 1),
        _block("b2", "TOGGLE", "1. Xem xét báo cáo doanh thu tháng 9", 2),
        _block("b3", "TOGGLE", "2. Thảo luận kế hoạch marketing tuần tới", 3),
        _block("b4", "TOGGLE", "3. Đánh giá hiệu suất đội ngũ", 4),
        _block("b5", "TEXT", "Ghi chú: Đảm bảo tất cả các nhiệm vụ đều được cập nhật trước buổi họp.", 5),
    ], [], []),
    # The "sub man" Page after the heading + checklist tests (kế hoạch tích to-do).
    "sub_man": _context("sub man", [
        _todo("t1", "Chuẩn bị release", False, 0),
        _todo("t2", "Kiểm tra hệ thống", False, 1),
        _todo("t3", "Tạo bản ghi kiểm tra", False, 2),
        _todo("t4", "Gửi thông báo cho đội", False, 3),
        _todo("t5", "in tài liệu", False, 4),
        _todo("t6", "đặt phòng", False, 5),
        _block("h1", "HEADER", "Việc tuần sau", 6),
        _todo("t7", "Cập nhật báo cáo", False, 7),
        _todo("t8", "Gửi email", True, 8),
    ], [], []),
    "release": _context("Release 2.0", [
        _block("r0", "HEADER", "Release 2.0", 0),
        {**_block("r1", "DATABASE_VIEW", "", 1), "content": None},
    ], [{
        "id": "db-tasks", "pageId": "page-1", "name": "Tasks",
        "properties": [
            _property("p-name", "Tên", "TITLE", "0"),
            _property("p-status", "Trạng thái", "SELECT", "1", [
                {"id": "o-todo", "name": "Todo", "color": None, "position": "0"},
                {"id": "o-done", "name": "Done", "color": None, "position": "1"},
            ]),
        ],
        "views": [{"id": "v-table", "databaseId": "db-tasks", "name": "Table", "type": "TABLE", "position": "0",
                   "properties": [{"propertyId": "p-name", "position": "0", "visible": True, "width": None},
                                  {"propertyId": "p-status", "position": "1", "visible": True, "width": None}]}],
        "rows": [{"id": "row-1", "databaseId": "db-tasks", "values": {"p-name": "Chuẩn bị changelog", "p-status": "o-done"}}],
    }], [{"blockId": "r1", "databaseId": "db-tasks", "viewId": "v-table"}]),
    # 2026-11-05: wider planner set (sections, toggle child, English page, second database).
    "study": _context("Ôn thi cuối kỳ", [
        _block("s0", "HEADER", "Môn Toán", 0),
        _todo("s1", "Làm đề năm 2023", False, 1),
        _todo("s2", "Ôn chương 3", False, 2),
        _block("s3", "HEADER", "Môn Lý", 3),
        _block("s4", "TEXT", "Ôn công thức dao động điều hoà", 4),
        _block("s5", "TOGGLE", "Tài liệu tham khảo", 5),
        {**_block("s6", "TEXT", "Sách giáo khoa lớp 12", 0), "parentBlockId": "s5"},
    ], [], []),
    "trip": _context("Trip to Hanoi", [
        _block("e0", "HEADER", "Packing", 0),
        _todo("e1", "Passport", False, 1),
        _todo("e2", "Phone charger", False, 2),
        _block("e3", "HEADER", "Itinerary", 3),
        _block("e4", "TEXT", "Day 1: Old Quarter walking tour", 4),
    ], [], []),
    "reading": _context("Đọc sách 2026", [
        _block("k0", "HEADER", "Danh sách đọc", 0),
        {**_block("k1", "DATABASE_VIEW", "", 1), "content": None},
    ], [{
        "id": "db-books", "pageId": "page-1", "name": "Sách",
        "properties": [
            _property("q-name", "Tên sách", "TITLE", "0"),
            _property("q-state", "Tình trạng", "SELECT", "1", [
                {"id": "o-reading", "name": "Đang đọc", "color": None, "position": "0"},
                {"id": "o-read", "name": "Đã đọc", "color": None, "position": "1"},
            ]),
        ],
        "views": [{"id": "v-books", "databaseId": "db-books", "name": "Bảng", "type": "TABLE", "position": "0",
                   "properties": [{"propertyId": "q-name", "position": "0", "visible": True, "width": None},
                                  {"propertyId": "q-state", "position": "1", "visible": True, "width": None}]}],
        "rows": [{"id": "row-b1", "databaseId": "db-books", "values": {"q-name": "Nhà giả kim", "q-state": "o-read"}}],
    }], [{"blockId": "k1", "databaseId": "db-books", "viewId": "v-books"}]),
}


def check_composition(draft: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    """Names of the failed expectations (empty list: the case passed)."""
    failed = []
    blocks = draft.get("blocks", [])
    todos = [_text(b["content"]["text"]) for b in blocks if b.get("type") == "TODO"]
    parents = {b.get("parentRef") for b in blocks}
    if "title" in expect and _text(draft["page"]["title"]) != _text(expect["title"]):
        failed.append("title")
    if expect.get("todo_texts") is not None and todos != [_text(t) for t in expect["todo_texts"]]:
        failed.append("todo_texts")
    if expect.get("min_todos", 0) > len(todos):
        failed.append("min_todos")
    if expect.get("no_todos") and todos:
        failed.append("no_todos")
    if expect.get("no_childless_toggles") and any(
        b.get("type") == "TOGGLE" and b.get("ref") not in parents for b in blocks
    ):
        failed.append("no_childless_toggles")
    if expect.get("min_toggles", 0) > sum(b.get("type") == "TOGGLE" for b in blocks):
        failed.append("min_toggles")
    # Embedded instructions ("… tạo 20 heading") must not be obeyed (gc10–gc12).
    if "max_headers" in expect and sum(b.get("type") == "HEADER" for b in blocks) > expect["max_headers"]:
        failed.append("max_headers")
    if any(b.get("type") in ("TODO", "TOGGLE") and strip_list_marker(b["content"]["text"]) != b["content"]["text"]
           for b in blocks):
        failed.append("no_numbering")
    if "databases" in expect and len(draft.get("databases", [])) != expect["databases"]:
        failed.append("databases")
    if expect.get("property_types"):
        found = {p["type"] for db in draft.get("databases", []) for p in db.get("properties", [])}
        if not set(expect["property_types"]) <= found:
            failed.append("property_types")
    if expect.get("select_options"):
        options = {_text(o["name"]) for db in draft.get("databases", []) for p in db.get("properties", [])
                   for o in p.get("options") or []}
        if not {_text(o) for o in expect["select_options"]} <= options:
            failed.append("select_options")
    return failed


def check_plan(plan: dict[str, Any], expect: dict[str, Any], context: dict[str, Any]) -> list[str]:
    failed = []
    operations = plan.get("operations", [])
    blocks = [b for op in operations if op.get("type") == "INSERT_BLOCKS" for b in op.get("blocks", [])]
    rows = [r for op in operations if op.get("type") == "CREATE_DATABASE_ROWS" for r in op.get("rows", [])]
    if plan.get("status") not in expect.get("status", ["PLAN_READY"]):
        failed.append("status")
    if "max_operations" in expect and len(operations) > expect["max_operations"]:
        failed.append("max_operations")
    if expect.get("operation_types") and [op.get("type") for op in operations] != expect["operation_types"]:
        failed.append("operation_types")
    if expect.get("block_types") is not None and [b.get("type") for b in blocks] != expect["block_types"]:
        failed.append("block_types")
    todos = [_text(b["content"]["text"]) for b in blocks if b.get("type") == "TODO"]
    if expect.get("todo_texts") is not None and todos != [_text(t) for t in expect["todo_texts"]]:
        failed.append("todo_texts")
    texts = [_text(b["content"].get("text", "")) for b in blocks if isinstance(b.get("content"), dict)]
    for needle in expect.get("texts_contain", []):
        if not any(_text(needle) in text for text in texts):
            failed.append("texts_contain")
            break
    ticks = [[op.get("text"), op.get("checked")] for op in operations if op.get("type") == "SET_TODO_CHECKED"]
    if "todo_updates" in expect and ticks != expect["todo_updates"]:
        failed.append("todo_updates")
    edits = [[op.get("oldText"), op.get("newText")] for op in operations if op.get("type") == "SET_BLOCK_TEXT"]
    if "text_edits" in expect and edits != expect["text_edits"]:
        failed.append("text_edits")
    deletes = [[op.get("text"), op.get("childCount")] for op in operations if op.get("type") == "DELETE_BLOCK"]
    if "deletes" in expect and deletes != expect["deletes"]:
        failed.append("deletes")
    if "max_new_blocks" in expect and len(blocks) > expect["max_new_blocks"]:
        failed.append("max_new_blocks")
    existing = {_text(b["content"]["text"]) for b in context["blocks"] if isinstance(b.get("content"), dict)}
    if any(text in existing for text in texts):
        failed.append("no_copy")
    if "after_block" in expect and any(op.get("afterBlockId") not in expect["after_block"]
                                       for op in operations if op.get("type") == "INSERT_BLOCKS"):
        failed.append("after_block")
    if "parent_block" in expect and any(op.get("parentBlockId") not in expect["parent_block"]
                                        for op in operations if op.get("type") == "INSERT_BLOCKS"):
        failed.append("parent_block")
    properties = [p for db in context["databases"] for p in db["properties"]]
    title_ids = {p["id"] for p in properties if p["type"] == "TITLE"}
    select_ids = {p["id"] for p in properties if p["type"] == "SELECT"}
    if "row_titles" in expect:
        titles = [_text(v) for r in rows for k, v in r.get("values", {}).items() if k in title_ids and isinstance(v, str)]
        if sorted(titles) != sorted(_text(t) for t in expect["row_titles"]):
            failed.append("row_titles")
    if "row_option" in expect:
        options = [v for r in rows for k, v in r.get("values", {}).items() if k in select_ids]
        if not rows or any(option != expect["row_option"] for option in options) or len(options) != len(rows):
            failed.append("row_option")
    return failed


def load_cases(path: Path, ids: set[str] | None, capability: str) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    return [c for c in cases if (not ids or c["id"] in ids) and capability in ("all", c["capability"])]


async def run_case(case: dict[str, Any], services: dict[str, Any], repeat: int) -> dict[str, Any]:
    from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
    from app.modules.page_composition.schemas.page_composition_schema import PageCompositionRequest

    runs = []
    for _ in range(repeat):
        started = perf_counter()
        try:
            if case["capability"] == "composition":
                # As NestJS sends it: a selection rides along as context.selectedText.
                selection = {"selectedText": case["selected_text"]} if case.get("selected_text") else None
                response = await services["composition"].process(
                    PageCompositionRequest(instruction=case["instruction"], context=selection))
                output = response.result.model_dump(mode="json")
                failed = check_composition(output, case["expect"])
            else:
                context = CONTEXTS[case["context"]]
                response = await services["planner"].process(
                    ModificationPlannerRequest(instruction=case["instruction"], context=context))
                output = response.result.model_dump(mode="json")
                failed = check_plan(output, case["expect"], context)
            runs.append({"ok": not failed, "failed": failed, "seconds": round(perf_counter() - started, 2),
                         **({"output": output} if failed else {})})  # Keep failing outputs for diagnosis.
        except Exception as exc:  # A provider/validation error is what users see as 502/504.
            runs.append({"ok": False, "error": type(exc).__name__, "seconds": round(perf_counter() - started, 2)})
    return {
        "id": case["id"], "capability": case["capability"], "instruction": case["instruction"],
        "passed": sum(r["ok"] for r in runs), "runs": len(runs),
        "errors": sum("error" in r for r in runs),
        "failedChecks": sorted({name for r in runs for name in r.get("failed", [])}),
        "avgSeconds": round(mean(r["seconds"] for r in runs), 2), "details": runs,
    }


def summarize(results: list[dict[str, Any]], models: dict[str, str]) -> dict[str, Any]:
    summary: dict[str, Any] = {"models": models}
    for capability in ("composition", "planner"):
        rows = [r for r in results if r["capability"] == capability]
        if not rows:
            continue
        runs = sum(r["runs"] for r in rows)
        summary[capability] = {
            "cases": len(rows), "runs": runs,
            "passRate": round(sum(r["passed"] for r in rows) / runs, 3),
            "errorRate": round(sum(r["errors"] for r in rows) / runs, 3),
            "casesAlwaysPassing": sum(r["passed"] == r["runs"] for r in rows),
            "avgSeconds": round(mean(r["avgSeconds"] for r in rows), 2),
            "failing": {r["id"]: r["failedChecks"] or ["error"] for r in rows if r["passed"] < r["runs"]},
        }
    return summary


async def main(args: argparse.Namespace) -> int:
    from app.core.config import get_settings
    from app.llm.providers.ollama import OllamaProvider
    from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
    from app.modules.page_composition.services.page_composition_service import PageCompositionService

    config = get_settings()
    models = {
        "composition": args.composition_model or args.model or config.ollama_page_composition_model or config.ollama_model,
        "planner": args.planner_model or args.model or config.ollama_modification_planner_model
        or config.ollama_page_composition_model or config.ollama_model,
    }
    providers = {
        name: OllamaProvider(base_url=config.ollama_base_url, model_name=model,
                             timeout_seconds=config.ollama_timeout_seconds, num_ctx=config.ollama_num_ctx,
                             num_gpu=(config.ollama_modification_planner_num_gpu if name == "planner" else None)
                             or config.ollama_num_gpu)
        for name, model in models.items()
    }
    try:
        services = {"composition": PageCompositionService(providers["composition"]),
                    "planner": ModificationPlannerService(providers["planner"])}
        cases = load_cases(args.cases, set(args.ids.split(",")) if args.ids else None, args.capability)
        results = []
        for case in cases:
            result = await run_case(case, services, args.repeat)
            results.append(result)
            print(f"{case['id']}: {result['passed']}/{result['runs']} "
                  f"{','.join(result['failedChecks']) or ('error' if result['errors'] else 'ok')} "
                  f"({result['avgSeconds']}s)", flush=True)
        report = {"summary": summarize(results, models), "cases": results}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        return 0
    finally:
        for provider in providers.values():
            await provider.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--capability", choices=["all", "composition", "planner"], default="all")
    parser.add_argument("--ids", help="Comma-separated case ids to run.")
    parser.add_argument("--repeat", type=int, default=3, help="Runs per case (models are not deterministic).")
    parser.add_argument("--model", help="Use this model for both capabilities.")
    parser.add_argument("--composition-model")
    parser.add_argument("--planner-model")
    parser.add_argument("--output", type=Path)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
