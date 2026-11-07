import pytest

from app.modules.page_composition.schemas.page_composition_schema import (
    PageCompositionDraft,
)
from app.modules.page_composition.services.task_blocks import normalize_task_blocks


def draft(*blocks: dict) -> PageCompositionDraft:
    return PageCompositionDraft.model_validate({
        "schemaVersion": 1,
        "type": "PAGE_COMPOSITION",
        "page": {"title": "Họp tuần"},
        "blocks": list(blocks),
        "databases": [],
    })


def toggle(ref: str, text: str) -> dict:
    return {"ref": ref, "type": "TOGGLE", "content": {"text": text}}


def kinds(result: PageCompositionDraft) -> list[tuple[str, str]]:
    return [(block.type, block.content.text) for block in result.blocks]


@pytest.mark.parametrize("instruction", [
    "Tạo trang họp tuần",
    "Tạo trang kế hoạch release gồm danh sách việc cần làm",
])
def test_list_like_toggles_become_unchecked_todos(instruction: str) -> None:
    result = normalize_task_blocks(draft(
        {"ref": "intro", "type": "TEXT", "content": {"text": "Các mục:"}},
        toggle("a", "- Xem xét tiến độ"),
        toggle("b", "2. Thảo luận kế hoạch"),
    ), instruction)
    assert kinds(result) == [
        ("TEXT", "Các mục:"), ("TODO", "Xem xét tiến độ"), ("TODO", "Thảo luận kế hoạch"),
    ]
    assert all(block.content.checked is False for block in result.blocks[1:])


def test_task_request_converts_unnumbered_toggles() -> None:
    result = normalize_task_blocks(draft(toggle("a", "Viết tài liệu")), "Tạo trang danh sách việc cần làm")
    assert kinds(result) == [("TODO", "Viết tài liệu")]


def test_keeps_toggles_with_children_faq_lines_and_explicit_requests() -> None:
    parent = draft(
        toggle("q", "Câu hỏi 1?"),
        {"ref": "a", "type": "TEXT", "content": {"text": "- Trả lời"}, "parentRef": "q"},
        toggle("faq", "Làm sao để đăng nhập?"),
    )
    # An empty TOGGLE does not open: it becomes a TEXT line (kế hoạch giới hạn 8 block).
    assert kinds(normalize_task_blocks(parent, "Tạo trang FAQ")) == [
        ("TOGGLE", "Câu hỏi 1?"), ("TEXT", "- Trả lời"), ("TEXT", "Làm sao để đăng nhập?")]
    explicit = draft(toggle("a", "- Mục 1"))
    assert normalize_task_blocks(explicit, "Tạo trang có các toggle cho từng mục") == explicit


def test_strips_numbering_from_existing_todos() -> None:
    result = normalize_task_blocks(draft(
        {"ref": "t", "type": "TODO", "content": {"text": "1. Gửi báo cáo", "checked": True}},
    ), "Tạo trang họp tuần")
    assert kinds(result) == [("TODO", "Gửi báo cáo")]
    assert result.blocks[0].content.checked is True


@pytest.mark.parametrize("instruction", ["Tạo trang họp tuần", "Tạo trang có toggle cho từng mục"])
def test_moves_children_of_non_toggle_blocks_to_root(instruction: str) -> None:
    # NestJS only accepts a TOGGLE parent; models nest items under a HEADER.
    result = normalize_task_blocks(draft(
        {"ref": "h", "type": "HEADER", "content": {"text": "Họp tuần"}, "styleConfig": {"level": 1}},
        {"ref": "a", "type": "TODO", "content": {"text": "Việc 1", "checked": False}, "parentRef": "h"},
        {"ref": "b", "type": "TEXT", "content": {"text": "Ghi chú"}, "parentRef": "missing"},
        toggle("t", "Chi tiết"),
        {"ref": "c", "type": "TEXT", "content": {"text": "Nội dung"}, "parentRef": "t"},
    ), instruction)
    assert [block.parentRef for block in result.blocks] == [None, None, None, None, "t"]
    assert [block.ref for block in result.blocks] == ["h", "a", "b", "t", "c"]


def test_toggles_under_a_task_heading_become_todos() -> None:
    # gc01: the model nested unnumbered agenda items under a task HEADER.
    result = normalize_task_blocks(draft(
        {"ref": "h", "type": "HEADER", "content": {"text": "Các nhiệm vụ cần hoàn thành:"}, "styleConfig": {"level": 2}},
        {**toggle("a", "Xem lại báo cáo tiến độ"), "parentRef": "h"},
        toggle("b", "Xác nhận lịch họp tuần tới"),
        {"ref": "faq", "type": "HEADER", "content": {"text": "Câu hỏi thường gặp"}, "styleConfig": {"level": 2}},
        toggle("q", "Làm sao để đăng nhập?"),
    ), "Tạo trang họp tuần")
    assert kinds(result) == [
        ("HEADER", "Các nhiệm vụ cần hoàn thành:"), ("TODO", "Xem lại báo cáo tiến độ"),
        ("TODO", "Xác nhận lịch họp tuần tới"), ("HEADER", "Câu hỏi thường gặp"),
        ("TEXT", "Làm sao để đăng nhập?"),
    ]
