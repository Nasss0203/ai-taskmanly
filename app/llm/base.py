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