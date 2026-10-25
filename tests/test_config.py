import pytest
from pydantic import ValidationError

from app.core.config import DEVELOPMENT_INTERNAL_TOKEN, Settings
from app.llm.factory import create_llm_provider
from app.llm.providers.fake import FakeLLMProvider


def test_internal_provider_defaults() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        ai_internal_token="test-token",
    )

    assert settings.llm_provider == "ollama"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "qwen3:4b"
    assert settings.ollama_timeout_seconds == 60.0


def test_continue_model_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_CONTINUE_MODEL", raising=False)
    assert Settings(_env_file=None, app_env="test").ollama_continue_model is None


@pytest.mark.parametrize("model", ["qwen3:4b-instruct", ""])
def test_continue_model_from_environment(
    monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    monkeypatch.setenv("OLLAMA_CONTINUE_MODEL", model)
    assert Settings(_env_file=None, app_env="test").ollama_continue_model == model


def test_production_rejects_development_internal_token() -> None:
    with pytest.raises(ValidationError, match="AI_INTERNAL_TOKEN"):
        Settings(
            _env_file=None,
            app_env="production",
            ai_internal_token=DEVELOPMENT_INTERNAL_TOKEN,
        )


def test_fake_provider_can_be_selected() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        ai_internal_token="test-token",
        llm_provider="fake",
    )

    assert isinstance(create_llm_provider(settings), FakeLLMProvider)


@pytest.mark.parametrize("environment", ["development", "production"])
@pytest.mark.parametrize("token", [
    "", "   ", DEVELOPMENT_INTERNAL_TOKEN, "short-secret", "a" * 64,
    "change-me-0123456789abcdef0123456789abcdef",
    "your-token-0123456789abcdef0123456789abcdef",
    "0123456789abcdef0123456789abcdef ",
    "replace-with-a-long-random-service-token",
    "0123456789abcdef" * 4,
], ids=["missing", "blank", "development", "short", "repeated", "change-me", "your-token", "whitespace", "env-example", "repeated-pattern"])
def test_non_test_environment_rejects_weak_tokens(environment, token):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, app_env=environment, ai_internal_token=token)
    assert "AI_INTERNAL_TOKEN" in str(error.value)
    if token.strip():
        assert token not in str(error.value)
        assert token not in repr(error.value)
        assert token not in error.value.json()


@pytest.mark.parametrize("environment", ["development", "production"])
def test_non_test_environment_requires_explicit_token(monkeypatch, environment):
    monkeypatch.delenv("AI_INTERNAL_TOKEN", raising=False)
    with pytest.raises(ValidationError, match="AI_INTERNAL_TOKEN"):
        Settings(_env_file=None, app_env=environment)


@pytest.mark.parametrize("environment", ["development", "production", "test"])
def test_strong_token_is_accepted_and_hidden(environment):
    # Synthetic fixture, never a deployment credential.
    token = "0123456789abcdefABCDEF9876543210_-"
    settings = Settings(_env_file=None, app_env=environment, ai_internal_token=token)
    assert settings.ai_internal_token.get_secret_value() == token
    assert token not in repr(settings)


@pytest.mark.parametrize("token", ["", "test-token"])
def test_test_environment_accepts_fixture_secrets(token):
    Settings(_env_file=None, app_env="test", ai_internal_token=token)


def test_test_environment_does_not_require_secret(monkeypatch):
    monkeypatch.delenv("AI_INTERNAL_TOKEN", raising=False)
    Settings(_env_file=None, app_env="test")


def test_token_is_hidden_when_another_setting_is_invalid():
    token = "0123456789abcdefABCDEF9876543210_-"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, app_env="invalid", ai_internal_token=token)
    assert token not in str(error.value)
    assert token not in error.value.json()
