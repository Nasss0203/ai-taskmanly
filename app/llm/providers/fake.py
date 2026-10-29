import hashlib
from typing import Any

from app.llm.base import EmbeddingResult, LLMGenerationResult


class FakeLLMProvider:
    """Deterministic provider for local smoke tests and automated tests."""

    provider_name = "fake"
    model_name = "fake-model"

    def __init__(
        self,
        response: str = "Fake AI response",
    ) -> None:
        self.response = response

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        return LLMGenerationResult(
            text=self.response,
        )

    async def close(self) -> None:
        return None


class FakeEmbeddingProvider:
    """Deterministic vectors for local smoke tests: same text, same vector."""

    provider_name = "fake"
    model_name = "fake-embedding"

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            embeddings=[
                [byte / 255 + 0.01 for byte in hashlib.sha256(text.encode()).digest()[: self.dimensions]]
                for text in texts
            ],
            model=self.model_name,
        )

    async def close(self) -> None:
        return None
