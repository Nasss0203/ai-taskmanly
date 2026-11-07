import asyncio

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiPageContext,
    ModificationPlannerRequest,
)
from app.modules.modification_planner.services.block_text import parse_block_text, plan_block_text
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from app.modules.modification_planner.services.todo_status import PLAN_ADAPTER
from app.modules.modification_planner.validators.modification_planner_semantic_validator import (
    ModificationPlannerSemanticValidationError,
    validate_modification_plan_semantics,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider

# The "sub man" Page a real user tested (kế hoạch sửa chữ block).
SUB_MAN = [
    ("x1", "TEXT", {"text": "ádasdasdasd"}),
    ("t1", "TODO", {"text": "Chuẩn bị release", "checked": False}),
    ("t4", "TODO", {"text": "Gửi thông báo cho đội", "checked": False}),
    ("t5", "TODO", {"text": "in tài liệu", "checked": False}),
    ("h1", "HEADER", {"text": "Việc tuần sau"}),
    ("t7", "TODO", {"text": "Cập nhật báo cáo", "checked": True}),
    ("t8", "TODO", {"text": "Gửi email", "checked": True}),
    ("db", "DATABASE_VIEW", None),
]


def context(blocks=SUB_MAN, truncated: bool = False) -> AiPageContext:
    return AiPageContext.model_validate({
        "schemaVersion": 1, "builtAt": "2026-10-26T00:00:00.000Z",
        "page": {"id": "page-1", "workspaceId": "w-1", "teamspaceId": None, "parentPageId": None,
                 "title": "sub man", "icon": None, "coverUrl": None, "updatedAt": "2026-10-26T00:00:00.000Z"},
        "blocks": [{
            "id": block_id, "parentBlockId": None, "type": kind, "orderIndex": index, "title": None,
            "content": content, "styleConfig": {"level": 2} if kind == "HEADER" else None, "dataConfig": None,
        } for index, (block_id, kind, content) in enumerate(blocks)],
        "databaseReferences": [], "databases": [],
        "completeness": {
            "blocks": {"total": len(blocks) + (5 if truncated else 0), "included": len(blocks), "truncated": truncated},
            "databases": {"total": 0, "included": 0, "truncated": False},
            "rows": [], "textTruncated": False,
        },
    })


@pytest.mark.parametrize(("instruction", "splits"), [
    ("đổi heading Việc tuần sau thành Việc tháng sau trong trang sub man",
     (("heading Việc tuần sau", "Việc tháng sau"),)),
    ("doi tuan sau thanh thang sau o trang sub man", (("tuan sau", "thang sau"),)),
    ('thay "in tài liệu" bằng "in tài liệu họp" trong trang sub man', (("in tài liệu", "in tài liệu họp"),)),
    ('change "Gửi email" to "Send email" on sub man page', (("Gửi email", "Send email"),)),
    ("hãy sửa to-do gửi email thành gửi email cho sếp nhé", (("to-do gửi email", "gửi email cho sếp"),)),
    # Every "thành" is a possible split; matching picks the one that names a block.
    ("đổi hoàn thành báo cáo thành xong báo cáo",
     (("hoàn", "báo cáo thành xong báo cáo"), ("hoàn thành báo cáo", "xong báo cáo"))),
])
def test_parses_every_phrasing(instruction, splits) -> None:
    assert parse_block_text(instruction).splits == splits


@pytest.mark.parametrize("instruction", [
    "đổi tên trang sub man thành abc",
    'Rename page "Q4" to "Q5"',
    "sửa heading hiện có",
    "thêm heading Kết luận",
    "tích gửi email trong trang sub man",
    "đổi thành abc",
])
def test_other_requests_are_not_text_edits(instruction) -> None:
    assert parse_block_text(instruction) is None


def ops(plan) -> list[tuple[str, str, str]]:
    assert plan.status == "PLAN_READY", plan
    return [(op.blockId, op.oldText, op.newText) for op in plan.operations]


def asked(plan) -> str:
    assert plan.status == "NEED_MORE_CONTEXT"
    [request] = plan.contextRequests
    assert request.reason == "AMBIGUOUS_TARGET" and request.question
    return request.description


def test_whole_text_with_a_filler_word_that_is_also_the_text() -> None:
    # "Việc" is a filler word and the first word of the heading.
    plan = plan_block_text("đổi heading Việc tuần sau thành Việc tháng sau trong trang sub man", context())
    assert ops(plan) == [("h1", "Việc tuần sau", "Việc tháng sau")]
    assert plan.summary == 'Sửa 1 block: "Việc tuần sau" → "Việc tháng sau"'


def test_part_of_one_block_replaces_only_that_part() -> None:
    plan = plan_block_text("sửa tuần sau thành tháng sau ở trang sub man", context())
    assert ops(plan) == [("h1", "Việc tuần sau", "Việc tháng sau")]


def test_part_typed_without_marks_keeps_the_rest_of_the_text() -> None:
    plan = plan_block_text("doi bao cao thanh ke hoach", context())
    assert ops(plan) == [("t7", "Cập nhật báo cáo", "Cập nhật ke hoach")]


def test_todo_text_changes_and_quotes_are_data() -> None:
    plan = plan_block_text('thay "in tài liệu" bằng "in tài liệu họp"', context())
    assert ops(plan) == [("t5", "in tài liệu", "in tài liệu họp")]


def test_part_in_several_blocks_is_asked() -> None:
    assert asked(plan_block_text("sửa gửi thành nhắn ở trang sub man", context())) == (
        '"gửi" có trong nhiều block: Gửi thông báo cho đội, Gửi email.'
    )


def test_part_repeated_in_one_block_is_asked() -> None:
    blocks = [("a", "TEXT", {"text": "Họp tuần này, báo cáo tuần sau"})]
    assert asked(plan_block_text("đổi tuần thành tháng", context(blocks))) == (
        '"tuần" xuất hiện 2 lần trong "Họp tuần này, báo cáo tuần sau".'
    )


def test_part_of_a_word_does_not_match() -> None:
    assert asked(plan_block_text("đổi tuầ thành tháng", context())).startswith('Không thấy "tuầ" trên trang.')


def test_unknown_text_lists_blocks_and_notes_a_cut_page() -> None:
    description = asked(plan_block_text("đổi abc thành xyz", context(truncated=True)))
    assert description == (
        'Không thấy "abc" trên trang. Các block đang có: ádasdasdasd, Chuẩn bị release, '
        "Gửi thông báo cho đội, in tài liệu, Việc tuần sau, Cập nhật báo cáo, Gửi email. "
        "Trang dài nên AI chỉ đọc được một phần."
    )


def test_same_text_in_two_blocks_is_asked() -> None:
    blocks = [("a", "TODO", {"text": "Gửi email", "checked": False}), ("b", "TEXT", {"text": "gửi email"})]
    assert asked(plan_block_text("đổi gửi email thành gửi thư", context(blocks))) == 'Có 2 block "Gửi email".'


def test_unchanged_text_is_reported_without_a_draft() -> None:
    assert asked(plan_block_text("đổi Gửi email thành Gửi email", context())) == '"Gửi email" đã như vậy rồi.'


def test_split_that_names_a_block_wins() -> None:
    blocks = [("a", "TODO", {"text": "Hoàn thành báo cáo", "checked": False})]
    plan = plan_block_text("đổi hoàn thành báo cáo thành xong báo cáo", context(blocks))
    assert ops(plan) == [("a", "Hoàn thành báo cáo", "xong báo cáo")]


def test_returns_none_for_other_requests() -> None:
    assert plan_block_text("thêm heading Kết luận", context()) is None


def edit_plan(*operations: dict):
    return PLAN_ADAPTER.validate_python({
        "schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": "page-1",
        "status": "PLAN_READY", "summary": "Sửa", "operations": list(operations),
    })


def edit(block_id: str = "h1", old: str = "Việc tuần sau", new: str = "Việc tháng sau") -> dict:
    return {"type": "SET_BLOCK_TEXT", "blockId": block_id, "oldText": old, "newText": new}


def test_validator_accepts_generated_plans() -> None:
    plan = plan_block_text("sửa tuần sau thành tháng sau", context())
    assert validate_modification_plan_semantics(plan, context()) is plan


@pytest.mark.parametrize(("operations", "message"), [
    ([edit("missing")], "not available"),
    ([edit("db", "x")], "no editable text"),
    ([edit(old="Việc tuần trước")], "does not match"),
    ([edit(new="Việc tuần sau")], "not changed"),
    ([edit(), edit(new="Khác")], "more than once"),
    ([edit("t8", "Gửi email", "Gửi thư"), {"type": "SET_TODO_CHECKED", "blockId": "t8", "text": "Gửi email",
                                           "checked": False}], "more than once"),
])
def test_validator_rejects_invalid_edits(operations, message) -> None:
    with pytest.raises(ModificationPlannerSemanticValidationError, match=message):
        validate_modification_plan_semantics(edit_plan(*operations), context())


def test_schema_limits_new_text() -> None:
    with pytest.raises(ValueError):
        edit_plan(edit(new="x" * 2001))


def test_planner_answers_text_edits_without_the_model() -> None:
    provider = FakeLLMProvider([])
    request = ModificationPlannerRequest(instruction="sửa tuần sau thành tháng sau trong trang sub man", context=context())
    response = asyncio.run(ModificationPlannerService(provider).process(request))
    assert provider.calls == []
    assert (response.provider, response.model) == ("rules", "block-text-v1")
    assert response.result.operations[0].newText == "Việc tháng sau"


def test_a_list_number_stays_when_the_new_text_has_none() -> None:
    # Live: "sửa Thảo luận kế hoạch … tuần tới thành … quý 4" dropped the "2.".
    from app.modules.modification_planner.schemas.modification_planner_schema import AiPageContext
    from app.modules.modification_planner.services.block_text import plan_block_text
    from scripts.evaluate_generation import CONTEXTS

    context = AiPageContext.model_validate(CONTEXTS["meeting"])
    plan = plan_block_text("sửa Thảo luận kế hoạch marketing tuần tới thành Thảo luận kế hoạch marketing quý 4", context)
    assert plan.operations[0].newText == "2. Thảo luận kế hoạch marketing quý 4"
    renumbered = plan_block_text("sửa Thảo luận kế hoạch marketing tuần tới thành 5. Kế hoạch quý 4", context)
    assert renumbered.operations[0].newText == "5. Kế hoạch quý 4"
