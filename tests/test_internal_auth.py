import sys
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings
from app.llm.base import LLMGenerationResult, LLMTokenUsage
from app.modules.writing.services import WritingService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


TEST_TOKEN = "test-internal-service-token"


@pytest.mark.parametrize(
    ("mode", "override", "separate"),
    [
        ("ollama", "qwen3:4b-instruct", True),
        ("ollama", None, False),
        ("ollama", "", False),
        ("ollama", "qwen3:1.7b", False),
        ("fake", "qwen3:4b-instruct", False),
    ],
)
def test_lifespan_routes_models_and_closes_providers(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    override: str | None,
    separate: bool,
) -> None:
    settings = Settings(
        _env_file=None,
        ai_internal_token=TEST_TOKEN,
        llm_provider=mode,
        ollama_model="qwen3:1.7b",
        ollama_continue_model=override,
    )
    default = FakeLLMProvider([" improved", " continuation"])
    default.model_name = "qwen3:1.7b"
    default.close = AsyncMock()
    continuation = FakeLLMProvider([" continuation"])
    continuation.model_name = "qwen3:4b-instruct"
    continuation.close = AsyncMock()
    factory = Mock(side_effect=[default, continuation])
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.create_llm_provider", factory)

    with TestClient(app) as client:
        for action in ["IMPROVE", "CONTINUE"]:
            response = client.post(
                "/internal/v1/writing",
                headers={"X-Internal-Service-Token": TEST_TOKEN},
                json={"action": action, "text": "Source"},
            )
            assert response.status_code == 200
            expected = continuation if separate and action == "CONTINUE" else default
            assert response.json()["model"] == expected.model_name
        assert factory.call_count == (2 if separate else 1)
        if separate:
            assert factory.call_args_list[1].args[0].ollama_model == override
        assert settings.ollama_model == "qwen3:1.7b"

    default.close.assert_awaited_once()
    if separate:
        continuation.close.assert_awaited_once()
    else:
        continuation.close.assert_not_awaited()


def test_lifespan_closes_default_when_override_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="ollama",
        ollama_model="qwen3:1.7b",
        ollama_continue_model="qwen3:4b-instruct",
    )
    provider = FakeLLMProvider([])
    provider.close = AsyncMock()
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.main.create_llm_provider",
        Mock(side_effect=[provider, RuntimeError("override creation failed")]),
    )

    with pytest.raises(RuntimeError, match="override creation failed"):
        with TestClient(app):
            pass

    provider.close.assert_awaited_once()


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
    assert response.json() == {
        "result": "Nội dung đã cải thiện.",
        "provider": "fake",
        "model": "fake-model",
    }
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
    assert response.json() == {
        "result": "Processed text",
        "provider": "fake",
        "model": "fake-model",
    }


def test_internal_writing_returns_usage(client: TestClient) -> None:
    client.app.state.writing_service = WritingService(FakeLLMProvider([
        LLMGenerationResult("Result", LLMTokenUsage(10, 5, 15))
    ]))
    response = client.post(
        "/internal/v1/writing",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"action": "IMPROVE", "text": "Source"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "result": "Result",
        "provider": "fake",
        "model": "fake-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_internal_writing_rejects_empty_text(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/writing",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"action": "IMPROVE", "text": ""},
    )

    assert response.status_code == 422
