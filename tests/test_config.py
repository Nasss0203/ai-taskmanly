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
