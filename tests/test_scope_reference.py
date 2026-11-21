"""M4 (kế hoạch lọc theo cấu trúc, E1–E2): a titled Page in a named place."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest, PageScopeModel
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_intent.services.page_reference_evidence import (
    PageScope,
    detect_page_reference,
    scoped_page_reference,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider

TEST_TOKEN = "test-internal-service-token"


@pytest.mark.parametrize(("source", "instruction", "title", "scope"), [
    ("thêm checklist gồm a, b vào trang Tasks trong trang Dự án A", "thêm checklist gồm a, b", "Tasks", PageScope("Dự án A")),
    ("Thêm checklist vào trang Tasks thuộc Dự án A", "Thêm checklist", "Tasks", PageScope("Dự án A")),
    ("thêm checklist vào trang Tasks của trang Dự án A", "thêm checklist", "Tasks", PageScope("Dự án A")),
    # No project entity: the words "dự án" stay, NestJS also tries without them.
    ("thêm checklist vào trang Tasks của dự án A", "thêm checklist", "Tasks", PageScope("dự án A")),
    ("tích gửi email trong trang Tasks trong teamspace Marketing", "tích gửi email", "Tasks", PageScope(None, "Marketing")),
    ('thêm checklist vào trang "Tasks" trong trang "Dự án A" nhé', "thêm checklist", "Tasks", PageScope("Dự án A")),
    ("add a checklist to the Tasks page in the Dự án A page", "add a checklist", "Tasks", PageScope("Dự án A")),
    ("add a checklist to the Tasks page in the Marketing teamspace", "add a checklist", "Tasks", PageScope(None, "Marketing")),
    ("add a checklist to the Tasks page in project Alpha", "add a checklist", "Tasks", PageScope("project Alpha")),
])
def test_recognises_a_page_and_its_place(source, instruction, title, scope) -> None:
    assert scoped_page_reference(source) == (instruction, title, scope)
    evidence = detect_page_reference(source)
    assert (evidence.reference_type, evidence.title, evidence.instruction, evidence.scope) == (
        "TITLE", title, instruction, scope,
    )


@pytest.mark.parametrize("source", [
    # "trong" without the kind of place is not a place ("this week").
    "thêm checklist vào trang Tasks trong tuần này",
    # Two target Pages, not a Page and its place.
    "chép gửi email từ trang A sang trang B",
    # Not an edit.
    "xem trang Tasks trong trang Dự án A",
    "tạo trang Tasks trong trang Dự án A",
    # No place at all.
    "thêm checklist vào trang sub man",
    "Thêm checklist vào trang tôi sửa hôm qua",
    # A whole sentence is not a name.
    "thêm checklist vào trang Tasks thuộc một hai ba bốn năm sáu bảy tám chín",
    # Another workspace is never a place here (s07); "của tôi" describes, not names.
    'Thêm checklist vào trang "Q4" của workspace khác',
    "thêm checklist vào trang Tasks của tôi",
])
def test_other_sentences_have_no_place(source) -> None:
    assert scoped_page_reference(source) is None
    assert detect_page_reference(source).scope is None


def test_page_intent_answers_without_the_model() -> None:
    provider = FakeLLMProvider([])
    response = asyncio.run(PageIntentService(provider).process(
        PageIntentRequest(instruction="thêm checklist gồm a, b vào trang Tasks trong trang Dự án A"),
    ))
    assert provider.calls == []
    assert (response.provider, response.model) == ("deterministic", "scoped-page-reference-v1")
    assert response.result.model_dump() == {
        "intent": "MODIFY_PAGE", "referenceType": "TITLE", "pageReference": "Tasks",
        "instruction": "thêm checklist gồm a, b", "needsClarification": False,
        "scope": {"parentTitle": "Dự án A", "teamspaceName": None},
    }


def test_a_scope_names_a_place() -> None:
    with pytest.raises(ValidationError):
        PageScopeModel.model_validate({"parentTitle": None, "teamspaceName": None})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with TestClient(app) as test_client:
        yield test_client


def test_http_adds_the_scope_key_only_with_a_place(client) -> None:
    """E2: NestJS checks keys strictly; other results keep the five keys."""
    client.app.state.page_intent_service = PageIntentService(FakeLLMProvider([]))
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": "add a checklist to the Tasks page in the Marketing teamspace"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == {
        "intent": "MODIFY_PAGE", "referenceType": "TITLE", "pageReference": "Tasks",
        "instruction": "add a checklist", "needsClarification": False,
        "scope": {"parentTitle": None, "teamspaceName": "Marketing"},
    }
