import asyncio

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from app.modules.modification_planner.services.explicit_plan import EXPLICIT_CONTENT_MODEL
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from app.modules.page_intent.services.page_reference_evidence import (
    detect_page_reference,
    source_backed_edit_instruction,
)
from scripts.evaluate_generation import CONTEXTS
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def read(instruction: str):
    evidence = detect_page_reference(instruction)
    return evidence.reference_type, evidence.title, source_backed_edit_instruction(instruction, evidence)


@pytest.mark.parametrize(("instruction", "title", "edit"), [  # D-31
    ("thêm heading Kết luận vào cuối trang Hội họp tuần", "Hội họp tuần", "thêm heading Kết luận vào cuối trang"),
    ("thêm heading Kết luận ở cuối trang Hội họp tuần", "Hội họp tuần", "thêm heading Kết luận ở cuối trang"),
    ("thêm to-do Gọi khách vào đầu trang Hội họp tuần", "Hội họp tuần", "thêm to-do Gọi khách vào đầu trang"),
    ("thêm heading Kết luận cuối trang Hội họp tuần", "Hội họp tuần", "thêm heading Kết luận vào cuối trang"),
    ('thêm đoạn văn "Thi vào sáng thứ Bảy" vào cuối trang Ôn thi cuối kỳ', "Ôn thi cuối kỳ",
     'thêm đoạn văn "Thi vào sáng thứ Bảy" vào cuối trang'),
])
def test_an_end_of_a_named_page_keeps_the_place_and_drops_the_name(instruction, title, edit) -> None:
    assert read(instruction) == ("TITLE", title, edit)


@pytest.mark.parametrize(("instruction", "title", "edit"), [  # D-30
    ("add a heading Day 2 at the end of the Trip to Hanoi page", "Trip to Hanoi",
     "add a heading Day 2 at the end of the page"),
    ("add a to-do Call the hotel to the end of the Trip page", "Trip", "add a to-do Call the hotel to the end of the page"),
    ("add a to-do Call the hotel at the top of the Trip page", "Trip", "add a to-do Call the hotel at the top of the page"),
    ("add a heading Notes to the bottom of the Trip page", "Trip", "add a heading Notes to the bottom of the page"),
])
def test_an_english_end_of_a_named_page_keeps_the_place(instruction, title, edit) -> None:
    assert read(instruction) == ("TITLE", title, edit)


@pytest.mark.parametrize(("instruction", "expected"), [
    ("thêm heading Kết luận vào trang Hội họp tuần", ("TITLE", "Hội họp tuần", "thêm heading Kết luận")),
    ("Ở cuối trang Hội họp tuần có gì?", None),
])
def test_other_page_names_read_as_before(instruction, expected) -> None:
    if expected is None:
        assert read(instruction)[2] is None
    else:
        assert read(instruction) == expected


@pytest.mark.parametrize(("instruction", "page", "after"), [
    ("thêm heading Kết luận vào cuối trang", "meeting", "b5"),
    ("add a heading Day 2 at the end of the page", "trip", "e4"),
])
def test_the_planner_places_the_kept_end_of_page(instruction, page, after) -> None:
    provider = FakeLLMProvider([])
    response = asyncio.run(ModificationPlannerService(provider).process(
        ModificationPlannerRequest(instruction=instruction, context=CONTEXTS[page])))
    assert provider.calls == [] and response.model == EXPLICIT_CONTENT_MODEL
    assert response.result.operations[0].afterBlockId == after
