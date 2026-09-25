import sys

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.writing.services import WritingService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


TEST_TOKEN = "test-internal-service-token"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with TestClient(app) as test_client:
        yield test_client


def test_internal_health_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/internal/v1/health")
    assert response.status_code == 401


def test_internal_health_rejects_wrong_token(client: TestClient) -> None:
    response = client.get(
        "/internal/v1/health",
        headers={"X-Internal-Service-Token": "wrong-token"},
    )
    assert response.status_code == 401


def test_internal_health_accepts_valid_token(client: TestClient) -> None:
    response = client.get(
        "/internal/v1/health",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Taskmanly AI",
    }
    assert "app.infrastructure.llm.qwen" not in sys.modules


def test_required_application_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert {
        "/api/v1/health",
        "/api/v1/assistant",
        "/internal/v1/health",
        "/internal/v1/writing",
    } <= paths


def test_internal_writing_uses_composed_service(client: TestClient) -> None:
    provider = FakeLLMProvider(["Nội dung đã cải thiện."])
    client.app.state.writing_service = WritingService(provider)

    response = client.post(
        "/internal/v1/writing",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"action": "IMPROVE", "text": "Nội dung gốc."},
    )

    assert response.status_code == 200
    assert response.json() == {"result": "Nội dung đã cải thiện."}
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "SHORTEN", "text": "Một nội dung cần được rút gọn."},
        {"action": "SUMMARIZE", "text": "Một nội dung cần được tóm tắt."},
        {"action": "TRANSLATE", "text": "Xin chào", "language": "English"},
    ],
)
def test_internal_writing_actions_return_result(
    client: TestClient,
    payload: dict[str, str],
) -> None:
    client.app.state.writing_service = WritingService(
        FakeLLMProvider(["Processed text"])
    )

    response = client.post(
        "/internal/v1/writing",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json() == {"result": "Processed text"}


def test_internal_writing_rejects_empty_text(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/writing",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"action": "IMPROVE", "text": ""},
    )

    assert response.status_code == 422
