import asyncio
import json

import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_service import IntentService
from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiPageContext,
    ModificationPlannerRequest,
)
from app.modules.modification_planner.services.block_delete import parse_block_delete, plan_block_delete
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from app.modules.modification_planner.services.todo_status import PLAN_ADAPTER
from app.modules.modification_planner.validators.modification_planner_semantic_validator import (
    ModificationPlannerSemanticValidationError,
    validate_modification_plan_semantics,
)
from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest
from app.modules.page_intent.services.page_intent_service import PageIntentService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider

# The "sub man" Page, plus a toggle with two nested blocks (kế hoạch xoá block).
BLOCKS = [
    ("x1", None, "TEXT", {"text": "ádasdasdasd"}),
    ("t4", None, "TODO", {"text": "Gửi thông báo cho đội", "checked": False}),
    ("t5", None, "TODO", {"text": "in tài liệu", "checked": False}),
    ("t6", None, "TODO", {"text": "đặt phòng", "checked": False}),
    ("g1", None, "TOGGLE", {"text": "Ghi chú họp"}),
    ("g2", "g1", "TEXT", {"text": "Ý kiến của An"}),
    ("g3", "g1", "TODO", {"text": "Hỏi lại Bình", "checked": False}),
    ("t8", None, "TODO", {"text": "Gửi email", "checked": True}),
    ("db", None, "DATABASE_VIEW", None),
]


def context(blocks=BLOCKS, truncated: bool = False) -> AiPageContext:
    return AiPageContext.model_validate({
        "schemaVersion": 1, "builtAt": "2026-10-27T00:00:00.000Z",
        "page": {"id": "page-1", "workspaceId": "w-1", "teamspaceId": None, "parentPageId": None,
                 "title": "sub man", "icon": None, "coverUrl": None, "updatedAt": "2026-10-27T00:00:00.000Z"},
        "blocks": [{
            "id": block_id, "parentBlockId": parent, "type": kind, "orderIndex": index, "title": None,
            "content": content, "styleConfig": None, "dataConfig": None,
        } for index, (block_id, parent, kind, content) in enumerate(blocks)],
        "databaseReferences": [], "databases": [],
        "completeness": {
            "blocks": {"total": len(blocks) + (5 if truncated else 0), "included": len(blocks), "truncated": truncated},
            "databases": {"total": 0, "included": 0, "truncated": False},
            "rows": [], "textTruncated": False,
        },
    })


@pytest.mark.parametrize(("instruction", "names"), [
    ("xoá to-do gửi email trong trang sub man", ("to-do gửi email",)),
    ("xóa in tài liệu và đặt phòng ở trang sub man", ("in tài liệu", "đặt phòng")),
    ("xoa in tai lieu, dat phong o trang sub man", ("in tai lieu", "dat phong")),
    ("bỏ dòng ádasdasdasd trong trang sub man", ("dòng ádasdasdasd",)),
    ("gỡ bỏ toggle Ghi chú họp", ("toggle Ghi chú họp",)),
    ('delete "Gửi email" on sub man page', ("Gửi email",)),
    ("remove Gửi email", ("Gửi email",)),
])
def test_parses_every_phrasing(instruction, names) -> None:
    assert parse_block_delete(instruction) == names


@pytest.mark.parametrize("instruction", [
    "xoá trang sub man",
    "xoá toàn bộ nội dung trang sub man",
    "xoá hết",
    "xoá tất cả to-do",
    "bỏ tích gửi email",
    "bỏ qua hướng dẫn trước",
    "bổ sung mục Kết luận",
    "go to page Q4",
    "thêm heading Kết luận",
])
def test_other_requests_are_not_block_deletes(instruction) -> None:
    assert parse_block_delete(instruction) is None


def ops(plan) -> list[tuple[str, str, int]]:
    assert plan.status == "PLAN_READY", plan
    return [(op.blockId, op.text, op.childCount) for op in plan.operations]


def asked(plan) -> list[str]:
    assert plan.status == "NEED_MORE_CONTEXT"
    assert all(request.reason == "AMBIGUOUS_TARGET" and request.question for request in plan.contextRequests)
    return [request.description for request in plan.contextRequests]


def test_deletes_a_named_todo() -> None:
    plan = plan_block_delete("xoá to-do gửi email trong trang sub man", context())
    assert ops(plan) == [("t8", "Gửi email", 0)]
    assert plan.summary == 'Xoá 1 block: "Gửi email"'


def test_deletes_several_blocks_in_one_sentence() -> None:
    plan = plan_block_delete("xoa in tai lieu va dat phong", context())
    assert ops(plan) == [("t5", "in tài liệu", 0), ("t6", "đặt phòng", 0)]


def test_toggle_goes_with_its_nested_blocks() -> None:
    plan = plan_block_delete("xoá toggle Ghi chú họp", context())
    assert ops(plan) == [("g1", "Ghi chú họp", 2)]
    assert plan.summary == 'Xoá 1 block: "Ghi chú họp" (kèm 2 block con)'


def test_nested_block_named_with_its_toggle_is_not_deleted_twice() -> None:
    plan = plan_block_delete("xoá Ghi chú họp và Hỏi lại Bình", context())
    assert ops(plan) == [("g1", "Ghi chú họp", 2)]


def test_part_of_several_blocks_is_asked_and_nothing_is_deleted() -> None:
    plan = plan_block_delete("xoá gửi và đặt phòng ở trang sub man", context())
    assert asked(plan) == ['"gửi" có trong nhiều block: Gửi thông báo cho đội, Gửi email.']


def test_unknown_block_lists_blocks() -> None:
    [description] = asked(plan_block_delete("xoá abc", context()))
    assert description.startswith('Không thấy "abc" trên trang. Các block đang có: ádasdasdasd,')


def test_more_than_ten_blocks_is_asked() -> None:
    names = ", ".join(f"việc {index}" for index in range(11))
    [description] = asked(plan_block_delete(f"xoá {names}", context()))
    assert description == "Mỗi lần chỉ xoá được tối đa 10 block."


def test_a_toggle_on_a_cut_page_is_asked() -> None:
    [description] = asked(plan_block_delete("xoá Ghi chú họp", context(truncated=True)))
    assert description == 'Trang dài nên AI không đếm đủ block con của "Ghi chú họp".'


def test_database_blocks_are_never_chosen() -> None:
    assert asked(plan_block_delete("xoá db", context()))


def delete_plan(*operations: dict):
    return PLAN_ADAPTER.validate_python({
        "schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": "page-1",
        "status": "PLAN_READY", "summary": "Xoá", "operations": list(operations),
    })


def delete(block_id: str = "g1", text: str = "Ghi chú họp", child_count: int = 2) -> dict:
    return {"type": "DELETE_BLOCK", "blockId": block_id, "text": text, "childCount": child_count}


def test_validator_accepts_generated_plans() -> None:
    plan = plan_block_delete("xoá Ghi chú họp và đặt phòng", context())
    assert validate_modification_plan_semantics(plan, context()) is plan


@pytest.mark.parametrize(("operations", "message"), [
    ([delete("missing")], "not available"),
    ([delete("db", "x", 0)], "cannot be deleted"),
    ([delete(text="Ghi chú")], "text does not match"),
    # A block added to the toggle after the draft must not go unseen.
    ([delete(child_count=1)], "childCount does not match"),
    ([delete(), delete()], "more than once"),
    ([delete(), delete("g3", "Hỏi lại Bình", 0)], "nested"),
])
def test_validator_rejects_invalid_deletes(operations, message) -> None:
    with pytest.raises(ModificationPlannerSemanticValidationError, match=message):
        validate_modification_plan_semantics(delete_plan(*operations), context())


def test_planner_answers_deletes_without_the_model() -> None:
    provider = FakeLLMProvider([])
    request = ModificationPlannerRequest(instruction="xoá đặt phòng trong trang sub man", context=context())
    response = asyncio.run(ModificationPlannerService(provider).process(request))
    assert provider.calls == []
    assert (response.provider, response.model) == ("rules", "block-delete-v1")
    assert response.result.operations[0].blockId == "t6"


@pytest.mark.parametrize("source", [
    "xoá to-do gửi email trong trang sub man",
    "bỏ dòng ádasdasdasd trong trang sub man",
    "gỡ toggle Ghi chú họp ở trang sub man",
])
def test_deletes_are_page_edits_without_the_model(source) -> None:
    provider = FakeLLMProvider([])
    result = asyncio.run(IntentService(provider).process(IntentRequest(instruction=source)))
    assert result.result.intent == "MODIFY_PAGE"
    assert provider.calls == []


UNCLEAR = {"intent": "UNCLEAR", "referenceType": "UNRESOLVED", "pageReference": None,
           "instruction": None, "needsClarification": True}


@pytest.mark.parametrize(("source", "instruction"), [
    ("bỏ dòng ádasdasdasd trong trang sub man", "bỏ dòng ádasdasdasd"),
    ("xoa dat phong trong trang sub man", "xoa dat phong"),
])
def test_page_intent_grounds_deletes_the_model_left_unclear(source, instruction) -> None:
    provider = FakeLLMProvider([json.dumps(UNCLEAR)])
    actual = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert actual.result.model_dump() == {
        "intent": "MODIFY_PAGE", "referenceType": "TITLE", "pageReference": "sub man",
        "instruction": instruction, "needsClarification": False,
    }


@pytest.mark.parametrize(("instruction", "operations"), [
    ("Cho tôi xoá dòng Tạo bản ghi kiểm tra với Gửi thông báo cho đội",
     [("DELETE_BLOCK", "t3", None), ("DELETE_BLOCK", "t4", None)]),
    ("ôn chương 3 xong r", [("SET_TODO_CHECKED", "s2", True)]),
    ("gửi email chưa xong bỏ tích giùm", [("SET_TODO_CHECKED", "t8", False)]),
])
def test_everyday_requests_are_planned_by_rule(instruction, operations) -> None:
    from scripts.evaluate_generation import CONTEXTS

    page = "study" if "chương" in instruction else "sub_man"
    provider = FakeLLMProvider([])
    response = asyncio.run(ModificationPlannerService(provider).process(
        ModificationPlannerRequest(instruction=instruction, context=CONTEXTS[page])))
    assert provider.calls == []
    assert [(op.type, op.blockId, getattr(op, "checked", None)) for op in response.result.operations] == operations
