from typing import Protocol


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
    ) -> str:
        ...

    async def close(self) -> None:
        ...
