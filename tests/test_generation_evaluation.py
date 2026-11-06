from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from scripts.evaluate_generation import CONTEXTS, DEFAULT_CASES, check_composition, check_plan, load_cases, summarize

KNOWN_EXPECTATIONS = {
    "title", "todo_texts", "min_todos", "no_todos", "no_childless_toggles", "min_toggles", "databases",
    "property_types", "select_options", "status", "max_operations", "operation_types", "block_types",
    "texts_contain", "max_new_blocks", "after_block", "parent_block", "row_titles", "row_option", "todo_updates", "text_edits", "deletes",
}


def todo(text: str) -> dict:
    return {"type": "TODO", "content": {"text": text, "checked": False}}


def draft(*blocks: dict, title: str = "Họp tuần", databases: list | None = None) -> dict:
    return {"page": {"title": title}, "blocks": list(blocks), "databases": databases or []}


def test_case_file_is_consistent() -> None:
    cases = load_cases(DEFAULT_CASES, None, "all")
    assert len({case["id"] for case in cases}) == len(cases) > 0
    for case in cases:
        assert set(case["expect"]) <= KNOWN_EXPECTATIONS, case["id"]
        if case["capability"] == "planner":
            ModificationPlannerRequest(instruction=case["instruction"], context=CONTEXTS[case["context"]])


def test_composition_checks() -> None:
    good = draft({"ref": "a", **todo("Tạo tài khoản")}, {"ref": "b", **todo("Đọc tài liệu")})
    assert check_composition(good, {"title": "họp tuần", "todo_texts": ["Tạo tài khoản", "Đọc tài liệu"],
                                     "no_childless_toggles": True, "databases": 0}) == []
    bad = draft({"ref": "a", "type": "TOGGLE", "content": {"text": "1. Tạo tài khoản"}}, title="Hội họp tuần")
    assert check_composition(bad, {"title": "Họp tuần", "min_todos": 1, "no_childless_toggles": True}) == [
        "title", "min_todos", "no_childless_toggles", "no_numbering",
    ]


def test_plan_checks_detect_copies_splits_and_inventions() -> None:
    context = CONTEXTS["meeting"]
    good = {"status": "PLAN_READY", "operations": [
        {"type": "INSERT_BLOCKS", "afterBlockId": "b5", "blocks": [todo("In tài liệu"), todo("Đặt phòng")]},
    ]}
    assert check_plan(good, {"max_operations": 1, "todo_texts": ["In tài liệu", "Đặt phòng"]}, context) == []
    split_copy = {"status": "PLAN_READY", "operations": [
        {"type": "INSERT_BLOCKS", "afterBlockId": "b1", "blocks": [todo("1. Xem xét báo cáo doanh thu tháng 9")]},
        {"type": "INSERT_BLOCKS", "afterBlockId": "b1", "blocks": [todo("Việc mới")]},
    ]}
    assert check_plan(split_copy, {"max_operations": 1, "max_new_blocks": 1, "after_block": ["b5"]}, context) == [
        "max_operations", "max_new_blocks", "no_copy", "after_block",
    ]


def test_plan_parent_check_requires_the_toggle() -> None:
    context = CONTEXTS["study"]
    plan = {"status": "PLAN_READY", "operations": [
        {"type": "INSERT_BLOCKS", "parentBlockId": "s5", "afterBlockId": "s6",
         "blocks": [{"type": "TEXT", "content": {"text": "Đề cương"}}]},
    ]}
    assert check_plan(plan, {"parent_block": ["s5"]}, context) == []
    plan["operations"][0]["parentBlockId"] = None
    assert check_plan(plan, {"parent_block": ["s5"]}, context) == ["parent_block"]


def test_plan_row_checks_use_title_and_select_properties() -> None:
    context = CONTEXTS["release"]
    plan = {"status": "PLAN_READY", "operations": [{"type": "CREATE_DATABASE_ROWS", "databaseId": "db-tasks",
            "rows": [{"values": {"p-name": "Sửa lỗi đăng nhập", "p-status": "o-todo"}}]}]}
    expect = {"operation_types": ["CREATE_DATABASE_ROWS"], "row_titles": ["Sửa lỗi đăng nhập"], "row_option": "o-todo"}
    assert check_plan(plan, expect, context) == []
    assert check_plan(plan, {**expect, "row_option": "o-done"}, context) == ["row_option"]


def test_summary_rates() -> None:
    results = [
        {"id": "a", "capability": "planner", "passed": 3, "runs": 3, "errors": 0, "failedChecks": [], "avgSeconds": 2},
        {"id": "b", "capability": "planner", "passed": 1, "runs": 3, "errors": 1, "failedChecks": ["no_copy"], "avgSeconds": 4},
    ]
    summary = summarize(results, {"planner": "m"})["planner"]
    assert summary == {"cases": 2, "runs": 6, "passRate": 0.667, "errorRate": 0.167, "casesAlwaysPassing": 1,
                       "avgSeconds": 3, "failing": {"b": ["no_copy"]}}


def test_plan_tick_checks_compare_text_and_state() -> None:
    plan = {"status": "PLAN_READY", "operations": [
        {"type": "SET_TODO_CHECKED", "blockId": "t6", "text": "đặt phòng", "checked": True},
    ]}
    context = CONTEXTS["sub_man"]
    assert check_plan(plan, {"todo_updates": [["đặt phòng", True]]}, context) == []
    assert check_plan(plan, {"todo_updates": [["đặt phòng", False]]}, context) == ["todo_updates"]
