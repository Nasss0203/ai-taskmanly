import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.page_intent.services.page_intent_service import PageIntentService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


TEST_TOKEN = "test-internal-service-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Service-Token": "bad"}])
def test_requires_internal_token(client, headers):
    response = client.post(
        "/internal/v1/page-intent",
        headers=headers,
        json={"instruction": "Thêm checklist vào page Release 2.0"},
    )
    assert response.status_code == 401


def test_structured_response(client):
    output = {
        "intent": "MODIFY_PAGE",
        "referenceType": "TITLE",
        "pageReference": "Release 2.0",
        "instruction": "Thêm checklist",
        "needsClarification": False,
    }
    provider = FakeLLMProvider([json.dumps(output)])
    client.app.state.page_intent_service = PageIntentService(provider)
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": "Thêm checklist vào page Release 2.0"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "result": output, "provider": "fake", "model": "fake-model"
    }
    assert len(provider.calls) == 1


@pytest.mark.parametrize("instruction", ["", "   "])
def test_request_validation(client, instruction):
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": instruction},
    )
    assert response.status_code == 422


def test_invalid_llm_response_is_502(client):
    client.app.state.page_intent_service = PageIntentService(
        FakeLLMProvider(['{"pageId":"hallucinated"}'])
    )
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": "Thêm checklist vào page Release 2.0"},
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "AI provider returned an invalid response."}


def test_explicit_named_page_edit_does_not_depend_on_model_output(client):
    provider = FakeLLMProvider([])
    client.app.state.page_intent_service = PageIntentService(provider)
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": 'Trong page tên "Release 2.0", hãy thêm checklist QA vào cuối trang.'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == {
        "intent": "MODIFY_PAGE",
        "referenceType": "TITLE",
        "pageReference": "Release 2.0",
        "instruction": "hãy thêm checklist QA vào cuối trang.",
        "needsClarification": False,
    }
    assert body["provider"] == "deterministic"
    assert provider.calls == []
