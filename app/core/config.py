from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEVELOPMENT_INTERNAL_TOKEN = "development-only-token"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    ai_internal_token: SecretStr = SecretStr(DEVELOPMENT_INTERNAL_TOKEN)

    llm_provider: Literal["ollama", "fake"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_continue_model: str | None = None
    ollama_page_composition_model: str | None = None
    ollama_timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def validate_production_token(self) -> "Settings":
        if (
            self.app_env == "production"
            and self.ai_internal_token.get_secret_value()
            == DEVELOPMENT_INTERNAL_TOKEN
        ):
            raise ValueError("AI_INTERNAL_TOKEN must be configured in production.")
        return self


def get_settings() -> Settings:
    return Settings()
