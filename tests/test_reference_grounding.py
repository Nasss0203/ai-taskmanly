"""M8 (kế hoạch ngữ cảnh RAG, I5): drafted items must come from the sources."""

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import (
    ModificationPlannerRequest,
)
from app.modules.modification_planner.services.modification_planner_service import (
    PLAN_ADAPTER,
    ModificationPlannerService,
)
from app.modules.modification_planner.services.reference_grounding import is_grounded
from tests.test_modification_planner_schema import make_context


PASSAGES = [
    "Bug blocker",
    "Ứng dụng bị crash khi tải ảnh lớn",
    "Không gửi được email xác nhận đăng ký",
    "QA: cần kiểm thử lại luồng thanh toán sau khi sửa giá",
]


@pytest.mark.parametrize(("text", "instruction", "expected"), [
    ("Ứng dụng bị crash khi tải ảnh lớn", "thêm checklist các bug blocker", True),
    # Reworded, but the passage's own words.
    ("Kiểm tra lại luồng thanh toán sau khi sửa giá", "thêm checklist kiểm tra", True),
    ("Bug blocker", "thêm checklist", True),
    # The user's own words.
    ("Rủi ro", "thêm mục rủi ro", True),
    # A prompt example the model copied, and tasks no passage holds.
    ("Chuẩn bị release", "thêm checklist", False),
    ("Tạo ticket cho từng bug blocker", "thêm checklist các bug blocker", False),
    # "bị" alone does not tie "chuẩn bị" to "bị crash".
    ("Chuẩn bị bản build", "thêm checklist", False),
])
def test_an_item_is_grounded_in_a_passage_or_the_request(text, instruction, expected) -> None:
    assert is_grounded(text, PASSAGES, instruction) is expected


def plan(*texts: str):
    return PLAN_ADAPTER.validate_python({
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "PLAN_READY",
        "summary": "thêm checklist",
        "operations": [{
            "type": "INSERT_BLOCKS",
            "parentBlockId": None,
            "afterBlockId": None,
            "blocks": [{"type": "TODO", "content": {"text": text, "checked": False}} for text in texts],
        }],
    })


def request(references):
    return ModificationPlannerRequest.model_validate({
        "instruction": "thêm checklist các bug blocker",
        "context": make_context(),
        "references": references,
    })


REFERENCES = [
    {"label": f"S{index + 1}", "pageTitle": "Bug tracker", "text": text}
    for index, text in enumerate(PASSAGES)
]


def test_invented_items_are_dropped() -> None:
    kept = ModificationPlannerService._keep_grounded_items(
        plan("Ứng dụng bị crash khi tải ảnh lớn", "Chuẩn bị release"), request(REFERENCES),
    )
    texts = [block.content.text for block in kept.operations[0].blocks]
    assert texts == ["Ứng dụng bị crash khi tải ảnh lớn"]


def test_nothing_left_means_the_source_did_not_hold_it() -> None:
    kept = ModificationPlannerService._keep_grounded_items(
        plan("Chuẩn bị release", "Tạo ticket cho từng bug blocker"), request(REFERENCES),
    )
    assert kept.status == "NEED_MORE_CONTEXT"
    assert kept.operations == []
    assert kept.contextRequests[0].reason == "MISSING_RESOURCE_CONTEXT"


def test_without_references_nothing_is_checked() -> None:
    original = plan("Chuẩn bị release")
    assert ModificationPlannerService._keep_grounded_items(original, request(None)) is original
