from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMTokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LLMGenerationResult:
    text: str
    usage: LLMTokenUsage | None = None
    provider_name: str | None = None
    model_name: str | None = None


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        ...

    async def close(self) -> None:
        ...


def answered_by(generation: LLMGenerationResult, provider: "LLMProvider") -> tuple[str, str]:
    return (generation.provider_name or provider.provider_name, generation.model_name or provider.model_name)


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: list[list[float]]
    model: str


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        ...

    async def close(self) -> None:
        ...