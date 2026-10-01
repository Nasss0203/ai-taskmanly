import json

import pytest
from fastapi.testclient import TestClient

from app.llm.base import LLMGenerationResult, LLMTokenUsage
from app.main import app
from app.modules.page_composition.services import PageCompositionService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


TEST_TOKEN = "test-internal-service-token"


def make_draft() -> dict:
    return {
        "schemaVersion": 1,
        "type": "PAGE_COMPOSITION",
        "page": {
            "title": "Project Planning",
        },
        "blocks": [],
        "databases": [],
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    with TestClient(app) as test_client:
        yield test_client


def test_page_composition_requires_internal_token(
    client: TestClient,
) -> None:
    response = client.post(
        "/internal/v1/page-composition",
        json={
            "instruction": "Tạo trang project planning.",
        },
    )

    assert response.status_code == 401


def test_page_composition_returns_generated_draft(
    client: TestClient,
) -> None:
    provider = FakeLLMProvider(
        [
            json.dumps(
                make_draft(),
                ensure_ascii=False,
            )
        ]
    )

    client.app.state.page_composition_service = PageCompositionService(
        provider,
    )

    response = client.post(
        "/internal/v1/page-composition",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json={
            "instruction": "Tạo trang project planning.",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
    "result": {
        "schemaVersion": 1,
        "type": "PAGE_COMPOSITION",
        "page": {
            "title": "Project Planning",
        },
        "blocks": [],
        "databases": [],
    },
    "provider": "fake",
    "model": "fake-model",
}

    assert len(provider.calls) == 1
    assert provider.calls[0]["max_new_tokens"] == 4000


def test_page_composition_returns_usage(
    client: TestClient,
) -> None:
    provider = FakeLLMProvider(
        [
            LLMGenerationResult(
                text=json.dumps(
                    make_draft(),
                    ensure_ascii=False,
                ),
                usage=LLMTokenUsage(
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                ),
            )
        ]
    )

    client.app.state.page_composition_service = PageCompositionService(
        provider,
    )

    response = client.post(
        "/internal/v1/page-composition",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json={
            "instruction": "Tạo trang project planning.",
        },
    )

    assert response.status_code == 200

    assert response.json()["usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }


def test_page_composition_invalid_llm_output_returns_502(
    client: TestClient,
) -> None:
    provider = FakeLLMProvider(
        [
            "not valid json",
        ]
    )

    client.app.state.page_composition_service = PageCompositionService(
        provider,
    )

    response = client.post(
        "/internal/v1/page-composition",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json={
            "instruction": "Tạo trang project planning.",
        },
    )

    assert response.status_code == 502

    assert response.json() == {
        "detail": "AI provider returned an invalid response.",
    }


def test_page_composition_rejects_empty_instruction(
    client: TestClient,
) -> None:
    response = client.post(
        "/internal/v1/page-composition",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json={
            "instruction": "",
        },
    )

    assert response.status_code == 422