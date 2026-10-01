from collections import deque
from typing import Any

from app.llm.base import LLMGenerationResult


class FakeLLMProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(
        self,
        responses: list[str | LLMGenerationResult],
    ) -> None:
        self._responses = deque(responses)
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_new_tokens": max_new_tokens,
                "response_schema": response_schema,
            }
        )

        if not self._responses:
            raise AssertionError(
                "FakeLLMProvider has no response left."
            )

        result = self._responses.popleft()

        return (
            LLMGenerationResult(text=result)
            if isinstance(result, str)
            else result
        )

    async def close(self) -> None:
        return None