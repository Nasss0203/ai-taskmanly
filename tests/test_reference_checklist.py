"""M8: a checklist of a named source Page's items, picked by rule."""

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import (
    ModificationPlannerReference,
)
from app.modules.modification_planner.services.reference_checklist import (
    plan_reference_checklist,
)


def bug_tracker() -> list[ModificationPlannerReference]:
    rows = [
        ("Bug blocker", None, True),
        ("Ứng dụng bị crash khi tải ảnh lớn", "Bug blocker", False),
        ("Không gửi được email xác nhận đăng ký", "Bug blocker", False),
        ("Lỗi nhỏ", None, True),
        ("- Nút Lưu bị lệch màu", "Lỗi nhỏ", False),
        ("Sai chính tả ở trang giới thiệu", "Lỗi nhỏ", False),
    ]
    return [
        ModificationPlannerReference.model_validate({
            "label": f"S{index + 1}", "pageTitle": "Bug tracker", "text": text,
            **({"section": section} if section else {}), "isHeading": heading,
        })
        for index, (text, section, heading) in enumerate(rows)
    ]


def items(plan) -> list[str]:
    return [block.content.text for block in plan.operations[0].blocks]


@pytest.mark.parametrize(("instruction", "expected"), [
    ("thêm checklist các bug blocker", ["Ứng dụng bị crash khi tải ảnh lớn", "Không gửi được email xác nhận đăng ký"]),
    ("Thêm checklist các lỗi nhỏ", ["Nút Lưu bị lệch màu", "Sai chính tả ở trang giới thiệu"]),
    # Without a topic: every item of the Page, never its headings.
    ("thêm checklist", [
        "Ứng dụng bị crash khi tải ảnh lớn", "Không gửi được email xác nhận đăng ký",
        "Nút Lưu bị lệch màu", "Sai chính tả ở trang giới thiệu",
    ]),
    # More words than the heading still name it.
    ("thêm checklist các bug blocker cần sửa gấp", ["Ứng dụng bị crash khi tải ảnh lớn", "Không gửi được email xác nhận đăng ký"]),
    ("add a checklist of the bug blockers", None),  # "blockers" is not "blocker": the model decides
])
def test_items_under_the_named_heading(instruction, expected) -> None:
    plan = plan_reference_checklist(instruction, "page-1", bug_tracker())
    if expected is None:
        assert plan is None
    else:
        assert plan.status == "PLAN_READY"
        assert items(plan) == expected
        assert all(block.type == "TODO" and block.content.checked is False for block in plan.operations[0].blocks)


@pytest.mark.parametrize("instruction", [
    # No heading names it: the model reads the passages.
    "thêm checklist các lỗi cần sửa",
    # Not a checklist.
    "thêm mục rủi ro",
    "thêm mục lỗi thanh toán",
])
def test_other_requests_go_to_the_model(instruction) -> None:
    assert plan_reference_checklist(instruction, "page-1", bug_tracker()) is None


def test_passages_found_by_topic_have_no_headings_to_pick_from() -> None:
    passages = [
        ModificationPlannerReference.model_validate({"label": "S1", "pageTitle": "QA", "text": "QA: Safari bị treo"}),
    ]
    assert plan_reference_checklist("thêm checklist", "page-1", passages) is None
    assert plan_reference_checklist("thêm checklist", "page-1", None) is None
