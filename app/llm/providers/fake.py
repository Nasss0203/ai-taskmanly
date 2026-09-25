class FakeLLMProvider:
    """Deterministic provider for local smoke tests and automated tests."""

    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, response: str = "Fake AI response") -> None:
        self.response = response

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
    ) -> str:
        return self.response

    async def close(self) -> None:
        return None
