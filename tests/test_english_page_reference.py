import asyncio

import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_rules import deterministic_result
from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_intent.services.page_reference_evidence import detect_page_reference
from tests.fakes.fake_async_llm_provider import FakeLLMProvider

PAGE_ID = "11111111-1111-4111-8111-111111111111"


def page_intent(instruction: str):
    provider = FakeLLMProvider([])
    response = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=instruction)))
    return response, provider.calls


@pytest.mark.parametrize(("instruction", "title", "edit"), [
    ("On the Trip to Hanoi page, add a to-do Call the client", "Trip to Hanoi", "add a to-do Call the client"),
    ("In the Trip to Hanoi page, add a to-do Call the client", "Trip to Hanoi", "add a to-do Call the client"),
    ('On the "Trip to Hanoi" page, add a to-do Call the client', "Trip to Hanoi", "add a to-do Call the client"),
    ("On the “Trip to Hanoi” page, add a to-do Call the client", "Trip to Hanoi", "add a to-do Call the client"),
    ("On the Trip page: add a to-do Call the client", "Trip", "add a to-do Call the client"),
    ("On the Trip page add a to-do Call the client", "Trip", "add a to-do Call the client"),
    ("On the Thử câu trộn page, add these tasks for recovery: Prepare post-run snacks and Join the Saturday group run",
     "Thử câu trộn",
     "add these tasks for recovery: Prepare post-run snacks and Join the Saturday group run"),
    ("In the Weekly sync page, mark Send agenda as done", "Weekly sync", "mark Send agenda as done"),
    ("On the Weekly sync page, change Send agenda to Send the agenda", "Weekly sync",
     "change Send agenda to Send the agenda"),
    ("On the Weekly sync page, delete the to-do Send agenda", "Weekly sync", "delete the to-do Send agenda"),
    ("add a to-do Call the client to the Trip page", "Trip", "add a to-do Call the client"),
    ("add a to-do Call the client on the Trip to Hanoi page", "Trip to Hanoi", "add a to-do Call the client"),
    ("add Deploy to staging to the Release page", "Release", "add Deploy to staging"),
])
def test_an_english_page_name_before_page_is_read_by_rule(instruction, title, edit) -> None:
    evidence = detect_page_reference(instruction)
    assert (evidence.reference_type, evidence.title, evidence.instruction) == ("TITLE", title, edit)
    response, calls = page_intent(instruction)
    assert calls == []
    assert (response.result.referenceType, response.result.pageReference, response.result.instruction) == (
        "TITLE", title, edit)
    intent = deterministic_result(IntentRequest(instruction=instruction))
    assert intent is not None and intent.intent == "MODIFY_PAGE" and not intent.needsClarification


def test_this_page_in_front_is_the_open_page() -> None:
    instruction = "On this page, add a to-do Call the client"
    evidence = detect_page_reference(instruction, has_current_page=True)
    assert (evidence.reference_type, evidence.instruction) == ("CURRENT_PAGE", "add a to-do Call the client")
    intent = deterministic_result(IntentRequest(instruction=instruction, currentPageId=PAGE_ID))
    assert intent is not None and intent.intent == "MODIFY_PAGE"


@pytest.mark.parametrize("instruction", [
    "add a heading Notes to the end of the page",
    "add a to-do X to the page about OAuth",
    "On the page I edited yesterday, add a to-do X",
    "On the A page and the B page, add a to-do X",
])
def test_a_place_a_description_or_two_pages_is_no_title(instruction) -> None:
    evidence = detect_page_reference(instruction)
    assert evidence.reference_type != "TITLE"


def test_a_question_about_a_page_stays_a_question() -> None:
    intent = deterministic_result(IntentRequest(instruction="On the Trip page, what is still open?"))
    assert intent is not None and intent.intent == "PAGE_QUESTION"


@pytest.mark.parametrize(("instruction", "edit"), [  # D-28
    ("delete the to-do Phone charger from the Trip to Hanoi page", "delete the to-do Phone charger"),
    ("uncheck Passport from the Trip to Hanoi page", "uncheck Passport"),
])
def test_from_the_page_names_the_whole_title(instruction, edit) -> None:
    evidence = detect_page_reference(instruction)
    assert (evidence.reference_type, evidence.title, evidence.instruction) == ("TITLE", "Trip to Hanoi", edit)


@pytest.mark.parametrize("instruction", [  # D-28
    "delete the Trip to Hanoi page",
    "remove the Trip to Hanoi page",
    "add a to-do Call the client to Trip to Hanoi page",
    "add a to-do Pack to Road to Rome page",
])
def test_a_title_holding_to_is_never_cut(instruction) -> None:
    assert detect_page_reference(instruction).title not in {"Hanoi", "Rome"}


@pytest.mark.parametrize(("instruction", "title"), [  # D-28
    ("add a to-do Call the client on the Trip to Hanoi page", "Trip to Hanoi"),
    ("add Deploy to staging to the Release page", "Release"),
    ("add a QA checklist to sub man page", "sub man"),
    ("add a heading Notes to the Road to Rome page", "Road to Rome"),
])
def test_titles_read_before_stay_the_same(instruction, title) -> None:
    assert detect_page_reference(instruction).title == title
