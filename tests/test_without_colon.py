"""Kế hoạch bỏ dấu hai chấm: people rarely type ":"; the same sentence without it
is read the same way (or left to the model when unsure)."""

import asyncio

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from app.modules.modification_planner.services.explicit_content import parse_explicit_blocks
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from app.modules.page_composition.services.content_lock import compose_explicit_page
from scripts.evaluate_generation import CONTEXTS
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


@pytest.mark.parametrize(("instruction", "expected"), [
    ("thêm checklist in tài liệu, đặt phòng", [("TODO", "In tài liệu"), ("TODO", "Đặt phòng")]),
    ("thêm việc chuẩn bị slide, gửi lịch", [("TODO", "Chuẩn bị slide"), ("TODO", "Gửi lịch")]),
    ("thêm checklist chuẩn bị họp quý bốn in tài liệu, đặt phòng", None),  # a topic may be in the first item
])
def test_listed_items_without_a_colon(instruction, expected) -> None:
    assert parse_explicit_blocks(instruction) == expected


def plan(page: str, instruction: str):
    request = ModificationPlannerRequest(instruction=instruction, context=CONTEXTS[page])
    return asyncio.run(ModificationPlannerService(FakeLLMProvider([])).process(request)).result


@pytest.mark.parametrize(("page", "instruction", "place", "expected"), [
    ("meeting", "ghi chú dời họp sang thứ Năm", (None, "b5"), [("TEXT", "dời họp sang thứ Năm")]),
    ("meeting", "ghi thêm vào Tuần họp dời họp sang thứ Năm", (None, "b5"), [("TEXT", "dời họp sang thứ Năm")]),
    ("sub_man", "thêm vào phần Việc tuần sau chuẩn bị slide, gửi lịch", (None, "t8"),
     [("TODO", "Chuẩn bị slide"), ("TODO", "Gửi lịch")]),
    ("meeting", "thêm vào phần Đánh giá hiệu suất đội ngũ chuẩn bị KPI, họp 1-1", ("b4", None),
     [("TODO", "Chuẩn bị KPI"), ("TODO", "Họp 1-1")]),
])
def test_a_place_named_without_a_colon(page, instruction, place, expected) -> None:
    result = plan(page, instruction)
    operation = result.operations[0]
    assert (operation.parentBlockId, operation.afterBlockId) == place
    assert [(b.type, b.content.text) for b in operation.blocks] == expected


def test_rows_after_the_table_name_without_a_colon() -> None:
    result = plan("release", "thêm 2 dòng vào bảng Tasks Viết test, Sửa lỗi")
    assert [row.values for row in result.operations[0].rows] == [{"p-name": "Viết test"}, {"p-name": "Sửa lỗi"}]


@pytest.mark.parametrize(("instruction", "title", "headers"), [
    ("tạo trang Kế hoạch Q1 3 phần Mục tiêu, Ngân sách, Rủi ro", "Kế hoạch Q1", ["Mục tiêu", "Ngân sách", "Rủi ro"]),
    ("tạo trang biên bản họp với các mục người tham dự, nội dung", "Biên bản họp", ["Người tham dự", "Nội dung"]),
])
def test_sections_of_a_new_page_without_a_colon(instruction, title, headers) -> None:
    draft = compose_explicit_page(instruction)
    assert draft.page.title == title
    assert [b.content.text for b in draft.blocks if b.type == "HEADER"] == headers


@pytest.mark.parametrize("instruction", [
    "tạo trang mua sắm sữa, trứng, rau",            # where does the title end?
    "tạo trang Công cụ gồm các phần mềm Jira, Slack",  # "phần mềm" is no section
])
def test_unsure_pages_are_left_to_the_model(instruction) -> None:
    assert compose_explicit_page(instruction) is None
