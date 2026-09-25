from collections import deque
from typing import Any


class FakeLLMProvider:
    """Deterministic provider used to characterize services without a model."""

    def __init__(self, responses: list[str]):
        self._responses = deque(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_new_tokens": max_new_tokens,
            }
        )

        if not self._responses:
            raise AssertionError("FakeLLMProvider has no response left.")

        return self._responses.popleft()
