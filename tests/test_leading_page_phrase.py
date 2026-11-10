import asyncio

import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_rules import deterministic_result
from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_intent.services.page_reference_evidence import (
    ActivityReference,
    activity_page_reference,
    detect_page_reference,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider

PAGE_ID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(("instruction", "edit", "reference"), [
    ("On the page I edited yesterday, add a to-do Call the client", "add a to-do Call the client",
     ActivityReference("YESTERDAY")),
    ("In the page I last edited, add a heading Notes", "add a heading Notes", ActivityReference("LATEST")),
    ("On the Trip page I edited yesterday, add a to-do Call the client", "add a to-do Call the client",
     ActivityReference("YESTERDAY", None, "Trip")),
    ("On the page that I updated 3 days ago: add a to-do Call the client", "add a to-do Call the client",
     ActivityReference("N_DAYS_AGO", 3)),
    ("Ở trang tôi sửa hôm qua, thêm to-do Gọi khách", "thêm to-do Gọi khách", ActivityReference("YESTERDAY")),
    ("Trong trang mình vừa sửa, thêm heading Tổng kết", "thêm heading Tổng kết", ActivityReference("LATEST")),
    ("Ở trang họp mà tôi sửa hôm qua thêm to-do Gọi khách", "thêm to-do Gọi khách",
     ActivityReference("YESTERDAY", None, "họp")),
])
def test_an_activity_page_named_first_is_read_by_rule(instruction, edit, reference) -> None:
    assert activity_page_reference(instruction) == (edit, reference)
    provider = FakeLLMProvider([])
    response = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=instruction)))
    assert provider.calls == []
    assert (response.result.referenceType, response.result.instruction) == ("ACTIVITY", edit)
    intent = deterministic_result(IntentRequest(instruction=instruction))
    assert intent is not None and intent.intent == "MODIFY_PAGE" and not intent.needsClarification


@pytest.mark.parametrize("instruction", [
    "Ở trang tôi sửa, thêm to-do Gọi khách",
    "On the page I edited in 2020, add a to-do Call the client",
    "Ở trang tôi sửa hôm qua, xem có gì",
])
def test_an_unsure_activity_page_is_left_as_before(instruction) -> None:
    assert activity_page_reference(instruction) is None


@pytest.mark.parametrize(("instruction", "edit"), [
    ("add a to-do Call the client to the page I edited yesterday", "add a to-do Call the client"),
    ("thêm to-do Gọi khách vào trang tôi sửa hôm qua", "thêm to-do Gọi khách"),
])
def test_an_activity_page_named_last_still_works(instruction, edit) -> None:
    assert activity_page_reference(instruction)[0] == edit


@pytest.mark.parametrize(("instruction", "edit"), [
    ("Ở trang này, thêm to-do Gọi khách", "thêm to-do Gọi khách"),
    ("Trong trang hiện tại, thêm to-do Gọi khách", "thêm to-do Gọi khách"),
    ("Ở trang này thêm to-do Gọi khách", "thêm to-do Gọi khách"),
    ("Trên trang đang mở: thêm heading Tổng kết", "thêm heading Tổng kết"),
])
def test_this_page_named_first_is_the_open_page(instruction, edit) -> None:
    evidence = detect_page_reference(instruction, has_current_page=True)
    assert (evidence.reference_type, evidence.instruction) == ("CURRENT_PAGE", edit)
    intent = deterministic_result(IntentRequest(instruction=instruction, currentPageId=PAGE_ID))
    assert intent is not None and intent.intent == "MODIFY_PAGE" and not intent.needsClarification


def test_this_page_with_a_question_is_no_edit() -> None:
    evidence = detect_page_reference("Ở trang này, có những việc gì", has_current_page=True)
    assert evidence.reference_type != "CURRENT_PAGE" or evidence.instruction is None
