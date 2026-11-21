"""M7 (kế hoạch tìm theo nội dung, H1): a Page named by words inside it."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_rules import deterministic_result
from app.modules.intent.services.intent_service import IntentService
from app.modules.page_intent.schemas.page_intent_schema import (
    ContentPageIntent,
    PageIntentRequest,
)
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_intent.services.page_reference_evidence import (
    content_page_reference,
    description_page_reference,
    detect_page_reference,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider

TEST_TOKEN = "test-internal-service-token"


@pytest.mark.parametrize(("source", "instruction", "topic"), [
    ("thêm checklist gồm a, b vào trang có nhắc tới quảng cáo Facebook", "thêm checklist gồm a, b", "quảng cáo Facebook"),
    ("thêm việc gọi khách vào trang có chứa ngân sách 50 triệu nhé", "thêm việc gọi khách", "ngân sách 50 triệu"),
    # One word is enough after "có nói về".
    ("thêm checklist vào trang có nói về OAuth", "thêm checklist", "OAuth"),
    ("thêm việc vào trang có ghi lịch họp tuần", "thêm việc", "lịch họp tuần"),
    # The Page first, then the edit.
    ("Tìm page có nói về OAuth rồi thêm checklist gồm test, review", "thêm checklist gồm test, review", "OAuth"),
    ("tìm trang có nhắc tới OAuth, thêm checklist gồm a, b", "thêm checklist gồm a, b", "OAuth"),
    ("hãy tìm trang nào có chứa release notes rồi thêm mục kiểm tra", "thêm mục kiểm tra", "release notes"),
    ("add a QA checklist to the page that mentions OAuth", "add a QA checklist", "OAuth"),
    ("find the page that mentions OAuth and add a QA checklist", "add a QA checklist", "OAuth"),
])
def test_recognises_a_page_by_its_content(source, instruction, topic) -> None:
    assert content_page_reference(source) == (instruction, topic)
    evidence = detect_page_reference(source)
    assert (evidence.reference_type, evidence.instruction, evidence.topic) == (
        "CONTENT", instruction, topic,
    )


@pytest.mark.parametrize("source", [
    # M6: "nói về" right after "trang" describes what the Page is for.
    "thêm checklist vào trang nói về OAuth login",
    # "ghi chú" is a note, not "có ghi" + words.
    "thêm việc vào trang có ghi chú công việc",
    # A quoted name is a title.
    'thêm việc vào trang "có chứa ngân sách"',
    # Only asking: no edit (H5).
    "tìm trang có nhắc tới release notes",
    "trang nào có nói về OAuth?",
    # Not an edit after the Page.
    "tìm trang có nói về OAuth rồi xem lại",
    # Two Pages.
    "chép việc từ trang có nói về OAuth sang trang có nói về SSO",
])
def test_other_sentences_are_not_content(source) -> None:
    assert content_page_reference(source) is None


def test_content_comes_before_description() -> None:
    source = "thêm checklist vào trang có nói về OAuth login"
    assert description_page_reference(source) is None
    assert detect_page_reference(source).reference_type == "CONTENT"


@pytest.mark.parametrize(("source", "intent"), [
    # "tìm …" with an edit is a Page modification (H1) ...
    ("Tìm page có nói về OAuth rồi thêm checklist gồm test, review", "MODIFY_PAGE"),
    ("find the page that mentions OAuth and add a QA checklist", "MODIFY_PAGE"),
    # ... and without one it stays a read-only request (H5).
    ("tìm trang có nhắc tới release notes", None),
])
def test_ask_routes_a_find_and_edit_sentence(source, intent) -> None:
    request = IntentRequest(instruction=source)
    decided = deterministic_result(request)
    # The service checks the rules' answer again; "tìm" must not undo it.
    routed = asyncio.run(IntentService(FakeLLMProvider([])).process(request)).result
    if intent is None:
        assert routed.intent != "MODIFY_PAGE"
    else:
        assert decided is not None and (decided.intent, decided.needsClarification) == (intent, False)
        assert (routed.intent, routed.needsClarification) == (intent, False)


def test_page_intent_answers_without_the_model() -> None:
    provider = FakeLLMProvider([])
    response = asyncio.run(PageIntentService(provider).process(
        PageIntentRequest(instruction="Tìm page có nói về OAuth rồi thêm checklist gồm test, review"),
    ))
    assert provider.calls == []
    assert (response.provider, response.model) == ("deterministic", "content-page-reference-v1")
    assert response.result.model_dump() == {
        "intent": "MODIFY_PAGE", "referenceType": "CONTENT", "pageReference": None,
        "instruction": "thêm checklist gồm test, review", "needsClarification": False,
        "topic": "OAuth",
    }


@pytest.mark.parametrize("change", [
    {"pageReference": "OAuth"},
    {"needsClarification": True},
    {"topic": ""},
    {"topic": None},
])
def test_a_content_result_is_strict(change) -> None:
    valid = {
        "intent": "MODIFY_PAGE", "referenceType": "CONTENT", "pageReference": None,
        "instruction": "thêm checklist", "needsClarification": False, "topic": "OAuth",
    }
    with pytest.raises(ValidationError):
        ContentPageIntent.model_validate({**valid, **change})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with TestClient(app) as test_client:
        yield test_client


def test_http_adds_the_topic_key_only_for_content(client) -> None:
    client.app.state.page_intent_service = PageIntentService(FakeLLMProvider([]))
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": "add a QA checklist to the page that mentions OAuth"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == {
        "intent": "MODIFY_PAGE", "referenceType": "CONTENT", "pageReference": None,
        "instruction": "add a QA checklist", "needsClarification": False, "topic": "OAuth",
    }
