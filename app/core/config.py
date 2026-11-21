import re
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEVELOPMENT_INTERNAL_TOKEN = "development-only-token"
TaskProvider = Literal["ollama", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    ai_internal_token: SecretStr = SecretStr("")

    llm_provider: Literal["ollama", "fake"] = "ollama"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"

    ollama_continue_model: str | None = None
    ollama_page_composition_model: str | None = None
    ollama_modification_planner_model: str | None = None
    # Intent and page-intent (short structured reads); unset keeps OLLAMA_MODEL.
    ollama_intent_model: str | None = None
    # Kế hoạch sửa tính năng viết (V3): dịch / tóm tắt / viết lại / rút gọn / mở rộng.
    # Unset keeps the old behaviour (OLLAMA_MODEL).
    ollama_writing_model: str | None = None

    ollama_num_ctx: int = 16384

    # Default GPU setting for Ollama providers.
    # None means no explicit num_gpu override.
    ollama_num_gpu: int | None = Field(default=None, ge=0)

    # GPU layers per model, whatever the job that calls it, e.g.
    # OLLAMA_MODEL_NUM_GPU={"qwen3:1.7b": 0, "qwen3:4b-instruct": 99}. On a
    # 4 GB GPU this puts the planner model wholly on the GPU and the intent
    # model on the CPU, instead of splitting the planner model across the
    # GPU and system RAM. It wins over OLLAMA_NUM_GPU and the planner's own.
    ollama_model_num_gpu: dict[str, int] = Field(default_factory=dict)

    # Dedicated GPU override for Modification Planner.
    ollama_modification_planner_num_gpu: int | None = Field(
        default=None,
        ge=0,
    )

    # Whole request (replies are streamed), and the longest silence between
    # two streamed lines: a model that stops sending tokens fails early.
    ollama_timeout_seconds: float = 60.0
    ollama_idle_timeout_seconds: float = Field(default=60.0, gt=0)

    # M5 (kế hoạch hạ tầng vector): Page text vectors. The CPU by default
    # (num_gpu 0), so the chat model keeps the 4 GB GPU.
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_embedding_num_gpu: int | None = Field(default=0, ge=0)
    ollama_embedding_timeout_seconds: float = Field(default=60.0, gt=0)

    writing_llm_provider: TaskProvider | None = None
    continue_llm_provider: TaskProvider | None = None
    page_composition_llm_provider: TaskProvider | None = None
    modification_planner_llm_provider: TaskProvider | None = None
    page_question_llm_provider: TaskProvider | None = None
    llm_fallback_to_ollama: bool = True

    gemini_api_key: SecretStr = SecretStr("")
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = Field(default=60.0, gt=0)
    gemini_thinking_level: Literal["MINIMAL", "LOW", "MEDIUM", "HIGH"] | None = "MINIMAL"
    gemini_thinking_tokens: int = Field(default=1024, ge=0)
    gemini_max_retries: int = Field(default=2, ge=0)

    @model_validator(mode="before")
    @classmethod
    def protect_token_in_validation_errors(cls, values: Any) -> Any:
        # BaseSettings builds its own input mapping. Wrap before any field or
        # model can fail so even ValidationError.json() redacts the secret.
        if isinstance(values, dict):
            for name in ("ai_internal_token", "gemini_api_key"):
                if isinstance(values.get(name), str):
                    values[name] = SecretStr(values[name])
        return values

    @field_validator("gemini_thinking_level", mode="before")
    @classmethod
    def empty_thinking_level_is_none(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value

    def task_uses_gemini(self) -> bool:
        return "gemini" in (
            self.writing_llm_provider, self.continue_llm_provider, self.page_composition_llm_provider,
            self.modification_planner_llm_provider, self.page_question_llm_provider,
        )

    @model_validator(mode="after")
    def require_gemini_key(self) -> "Settings":
        if self.task_uses_gemini() and not self.gemini_api_key.get_secret_value().strip():
            raise ValueError("GEMINI_API_KEY is required when a task uses the gemini provider.")
        return self

    @model_validator(mode="after")
    def validate_internal_token(self) -> "Settings":
        if self.app_env == "test":
            return self

        token = self.ai_internal_token.get_secret_value()
        normalized = re.sub(r"[^a-z0-9]", "", token.casefold())
        placeholders = (
            "development", "changeme", "replaceme", "replacewith", "placeholder",
            "yourtoken", "yourinternal", "yoursecret", "example", "testtoken", "password",
        )
        # A format check cannot prove entropy: deployment secrets must be
        # randomly generated. Accept hex/base64url without imposing an alphabet.
        if (
            len(token) < 32
            or not token.isascii()
            or not token.isprintable()
            or any(char.isspace() for char in token)
            or len(set(token)) < 12
            or any(marker in normalized for marker in placeholders)
            or any(
                token == token[:size] * (len(token) // size)
                for size in range(1, len(token) // 2 + 1)
                if len(token) % size == 0
            )
        ):
            raise ValueError(
                "AI_INTERNAL_TOKEN must be a randomly generated secret with "
                "at least 32 printable ASCII characters, no whitespace, "
                "at least 12 distinct characters, no repeated pattern, "
                "and no placeholder text."
            )

        return self


def get_settings() -> Settings:
    return Settings()
