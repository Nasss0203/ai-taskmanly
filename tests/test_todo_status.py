import asyncio

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiPageContext,
    ModificationPlannerRequest,
)
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from app.modules.modification_planner.services.todo_status import PLAN_ADAPTER, parse_todo_status, plan_todo_status
from app.modules.modification_planner.validators.modification_planner_semantic_validator import (
    ModificationPlannerSemanticValidationError,
    validate_modification_plan_semantics,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider

# The to-dos of the "sub man" Page a real user tested.
SUB_MAN = [
    ("t1", "Chuẩn bị release", False),
    ("t2", "Kiểm tra hệ thống", False),
    ("t3", "Tạo bản ghi kiểm tra", False),
    ("t4", "Gửi thông báo cho đội", False),
    ("t5", "in tài liệu", False),
    ("t6", "đặt phòng", False),
    ("t7", "Cập nhật báo cáo", False),
    ("t8", "Gửi email", True),
]


def context(todos=SUB_MAN, truncated: bool = False) -> AiPageContext:
    blocks = [{
        "id": "h1", "parentBlockId": None, "type": "HEADER", "orderIndex": 0, "title": None,
        "content": {"text": "Việc tuần sau"}, "styleConfig": {"level": 2}, "dataConfig": None,
    }] + [{
        "id": block_id, "parentBlockId": None, "type": "TODO", "orderIndex": index + 1, "title": None,
        "content": {"text": text, "checked": checked}, "styleConfig": None, "dataConfig": None,
    } for index, (block_id, text, checked) in enumerate(todos)]
    return AiPageContext.model_validate({
        "schemaVersion": 1, "builtAt": "2026-10-26T00:00:00.000Z",
        "page": {"id": "page-1", "workspaceId": "w-1", "teamspaceId": None, "parentPageId": None,
                 "title": "sub man", "icon": None, "coverUrl": None, "updatedAt": "2026-10-26T00:00:00.000Z"},
        "blocks": blocks, "databaseReferences": [], "databases": [],
        "completeness": {
            "blocks": {"total": len(blocks) + (5 if truncated else 0), "included": len(blocks), "truncated": truncated},
            "databases": {"total": 0, "included": 0, "truncated": False},
            "rows": [], "textTruncated": False,
        },
    })


def parsed(instruction: str) -> tuple[bool, list[str], bool] | None:
    request = parse_todo_status(instruction)
    return request and (request.checked, [item.text for item in request.items], request.item_first)


@pytest.mark.parametrize(("instruction", "expected"), [
    # T1
    ("tích gửi email trong trang sub man", (True, ["gửi email"], False)),
    ("tich gui email trong trang sub man", (True, ["gui email"], False)),
    ('check "Gửi email" on sub man page', (True, ["Gửi email"], False)),
    ("hãy tích mục gửi email và cập nhật báo cáo ở trang sub man nhé", (True, ["gửi email", "cập nhật báo cáo"], False)),
    # T2
    ("đánh dấu cập nhật báo cáo và gửi email là đã xong ở trang sub man",
     (True, ["cập nhật báo cáo", "gửi email"], False)),
    ("mark gửi email as done", (True, ["gửi email"], False)),
    # T3
    ("đánh dấu đã hoàn thành phần gửi email ở trang sub man", (True, ["gửi email"], False)),
    ("danh dau da hoan thanh phan gui email o trang sub man", (True, ["gui email"], False)),
    # T4
    ("hoàn thành gửi email trong trang sub man", (True, ["gửi email"], False)),
    ("làm xong in tài liệu và đặt phòng ở trang sub man", (True, ["in tài liệu", "đặt phòng"], False)),
    # T5: names first, status words never become part of a name.
    ("gửi email xong rồi, trong trang sub man", (True, ["gửi email"], True)),
    ("tạo bản ghi xong rồi, trong trang sub man", (True, ["tạo bản ghi"], True)),
    ("in tài liệu, đặt phòng đã hoàn thành ở trang sub man", (True, ["in tài liệu", "đặt phòng"], True)),
    # B1–B3
    ("bỏ tích in tài liệu trong trang sub man", (False, ["in tài liệu"], False)),
    ("uncheck Gửi email", (False, ["Gửi email"], False)),
    ("đánh dấu gửi email là chưa xong ở trang sub man", (False, ["gửi email"], False)),
    ("gửi email chưa hoàn thành trong trang sub man", (False, ["gửi email"], True)),
])
def test_parses_every_phrasing(instruction, expected) -> None:
    assert parsed(instruction) == expected


@pytest.mark.parametrize("instruction", [
    "thêm checklist gồm in tài liệu vào trang sub man",
    "thêm heading Kết luận ở cuối trang",
    "tích hợp Slack vào trang sub man",
    "thêm check list vào trang sub man",
    "hoàn thành trang sub man",
    "đánh dấu trang này là quan trọng",
    "tóm tắt trang sub man",
])
def test_other_requests_are_not_ticks(instruction) -> None:
    assert parse_todo_status(instruction) is None


def ops(plan) -> list[tuple[str, str, bool]]:
    return [(op.blockId, op.text, op.checked) for op in plan.operations]


def asked(plan) -> list[str]:
    assert plan.status == "NEED_MORE_CONTEXT"
    assert all(request.reason == "AMBIGUOUS_TARGET" and request.question for request in plan.contextRequests)
    return [request.description for request in plan.contextRequests]


def test_exact_names_ignore_case_and_marks() -> None:
    plan = plan_todo_status("tich cap nhat bao cao va IN TAI LIEU trong trang sub man", context())
    assert plan.status == "PLAN_READY"
    assert ops(plan) == [("t7", "Cập nhật báo cáo", True), ("t5", "in tài liệu", True)]
    assert plan.summary == "Tích 2 to-do: Cập nhật báo cáo, in tài liệu"


def test_partial_name_of_exactly_one_todo() -> None:
    plan = plan_todo_status("làm xong phần chuẩn bị ở trang sub man", context())
    assert ops(plan) == [("t1", "Chuẩn bị release", True)]


def test_exact_name_wins_over_a_longer_todo() -> None:
    todos = [("a", "Gửi email", False), ("b", "Gửi email cho sếp", False)]
    assert ops(plan_todo_status("tích gửi email", context(todos))) == [("a", "Gửi email", True)]


def test_partial_name_of_several_todos_is_asked() -> None:
    # Even though only "Gửi thông báo cho đội" would change: a part is never narrowed.
    [description] = asked(plan_todo_status("tích gửi ở trang sub man", context()))
    assert description == '"gửi" khớp nhiều to-do: Gửi thông báo cho đội, Gửi email.'


def test_part_of_a_word_does_not_match() -> None:
    [description] = asked(plan_todo_status("tích gu ở trang sub man", context()))
    assert description.startswith('Không thấy to-do "gu" trên trang. Các to-do đang có: Chuẩn bị release')


def test_too_short_name_is_asked() -> None:
    todos = [("a", "A", False)]
    assert asked(plan_todo_status("tích a", context(todos)))


def test_unknown_name_lists_todos_and_notes_a_cut_page() -> None:
    many = [(f"t{index}", f"Việc {index}", False) for index in range(12)]
    [description] = asked(plan_todo_status("tích gửi báo cáo", context(many, truncated=True)))
    assert description == (
        'Không thấy to-do "gửi báo cáo" trên trang. Các to-do đang có: '
        + ", ".join(f"Việc {index}" for index in range(10))
        + "…. Trang dài nên AI chỉ đọc được một phần."
    )


def test_duplicate_names_are_asked() -> None:
    todos = [("a", "Gửi email", False), ("b", "gửi email", False)]
    [description] = asked(plan_todo_status("tích gửi email", context(todos)))
    assert description == 'Có 2 to-do "Gửi email".'


def test_duplicate_names_prefer_the_one_that_changes() -> None:
    todos = [("a", "Gửi email", True), ("b", "Gửi email", False)]
    assert ops(plan_todo_status("tích gửi email", context(todos))) == [("b", "Gửi email", True)]


def test_two_names_for_one_todo_are_asked() -> None:
    [description] = asked(plan_todo_status("tích chuẩn bị và release", context()))
    assert description == '"chuẩn bị" và "release" cùng chỉ to-do "Chuẩn bị release".'


def test_already_ticked_is_reported_without_a_draft() -> None:
    [description] = asked(plan_todo_status("tích gửi email trong trang sub man", context()))
    assert description == '"Gửi email" đã được tích rồi.'


def test_already_ticked_items_are_skipped_when_others_change() -> None:
    plan = plan_todo_status("tích gửi email và đặt phòng", context())
    assert ops(plan) == [("t6", "đặt phòng", True)]
    assert plan.summary == 'Tích 1 to-do: đặt phòng (bỏ qua "Gửi email" vì đã được tích rồi)'


def test_untick() -> None:
    plan = plan_todo_status("bỏ tích gửi email trong trang sub man", context())
    assert ops(plan) == [("t8", "Gửi email", False)]
    assert plan.summary == "Bỏ tích 1 to-do: Gửi email"
    [description] = asked(plan_todo_status("bỏ tích đặt phòng", context()))
    assert description == '"đặt phòng" đang chưa được tích.'


@pytest.mark.parametrize("instruction", [
    # An insert phrased names-first that matches no to-do keeps the normal planner.
    "thêm mục Hoàn thành xong rồi",
    "thêm checklist gồm in tài liệu vào trang sub man",
])
def test_returns_none_for_the_normal_planner(instruction) -> None:
    assert plan_todo_status(instruction, context()) is None


def test_names_first_sentence_without_a_match_is_asked_not_inserted() -> None:
    [description] = asked(plan_todo_status("báo cáo tuần xong rồi", context()))
    assert description.startswith('Không thấy to-do "báo cáo tuần" trên trang.')


def test_names_first_sentence_with_a_match_is_a_tick() -> None:
    plan = plan_todo_status("tạo bản ghi xong rồi, trong trang sub man", context())
    assert ops(plan) == [("t3", "Tạo bản ghi kiểm tra", True)]


def tick_plan(*operations: dict):
    return PLAN_ADAPTER.validate_python({
        "schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": "page-1",
        "status": "PLAN_READY", "summary": "Tích", "operations": list(operations),
    })


def tick(block_id: str = "t6", text: str = "đặt phòng") -> dict:
    return {"type": "SET_TODO_CHECKED", "blockId": block_id, "text": text, "checked": True}


def test_validator_accepts_the_generated_plans() -> None:
    plan = plan_todo_status("tích đặt phòng và in tài liệu", context())
    assert validate_modification_plan_semantics(plan, context()) is plan


@pytest.mark.parametrize(("operations", "message"), [
    ([tick("missing")], "not available"),
    ([tick("h1", "Việc tuần sau")], "is not a to-do"),
    # text is only shown; it can never rename the to-do.
    ([tick("t6", "Đặt phòng họp")], "text does not match"),
    ([tick(), tick()], "more than once"),
])
def test_validator_rejects_invalid_ticks(operations, message) -> None:
    with pytest.raises(ModificationPlannerSemanticValidationError, match=message):
        validate_modification_plan_semantics(tick_plan(*operations), context())


def run_planner(instruction: str) -> tuple[object, FakeLLMProvider]:
    provider = FakeLLMProvider([])
    request = ModificationPlannerRequest(instruction=instruction, context=context())
    return asyncio.run(ModificationPlannerService(provider).process(request)), provider


@pytest.mark.parametrize("instruction", [
    "tích đặt phòng trong trang sub man",
    "tích gửi ở trang sub man",
])
def test_planner_answers_ticks_without_the_model(instruction) -> None:
    response, provider = run_planner(instruction)
    assert provider.calls == []
    assert (response.provider, response.model) == ("rules", "todo-status-v1")
    assert response.usage is None


def test_planner_keeps_the_model_for_other_requests() -> None:
    # An insert phrased names-first that matches no to-do: the model routes it.
    with pytest.raises(AssertionError, match="no response left"):
        run_planner("thêm mục Hoàn thành xong rồi")
