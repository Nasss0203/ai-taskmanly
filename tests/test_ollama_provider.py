import asyncio
import json

import httpx
import pytest

from app.core.exceptions import InvalidLLMResponseError
from app.llm.providers.ollama import OllamaProvider


def test_ollama_provider_calls_chat_api() -> None:
    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert request.url.path == "/api/chat"
            assert payload["model"] == "qwen3:4b"
            assert payload["stream"] is False
            assert payload["think"] is False
            assert payload["options"]["num_predict"] == 250
            return httpx.Response(
                200,
                json={"message": {"content": "Kết quả"}},
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider(
                base_url="http://unused.test",
                model_name="qwen3:4b",
                timeout_seconds=1,
                client=client,
            )
            result = await provider.generate("system", "user", 250)
            assert result == "Kết quả"

    asyncio.run(run_test())


def test_ollama_provider_rejects_invalid_response() -> None:
    async def run_test() -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"done": True})
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider(
                base_url="http://unused.test",
                model_name="qwen3:4b",
                timeout_seconds=1,
                client=client,
            )
            with pytest.raises(InvalidLLMResponseError):
                await provider.generate("system", "user")

    asyncio.run(run_test())
