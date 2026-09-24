from typing import Protocol


class LLMProvider(Protocol):
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
    ) -> str:
        ...
