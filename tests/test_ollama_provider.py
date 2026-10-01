import asyncio
import json

import httpx
import pytest

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMTokenUsage
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

            assert "format" not in payload
            assert "temperature" not in payload["options"]

            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": " continuation text ",
                    },
                },
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

            result = await provider.generate(
                "system",
                "user",
                250,
            )

            assert result.text == " continuation text "
            assert result.usage is None

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        (
            {
                "prompt_eval_count": 314,
                "eval_count": 38,
            },
            LLMTokenUsage(
                314,
                38,
                352,
            ),
        ),
        (
            {
                "prompt_eval_count": 0,
                "eval_count": 0,
            },
            LLMTokenUsage(
                0,
                0,
                0,
            ),
        ),
        (
            {},
            None,
        ),
        (
            {
                "prompt_eval_count": 10,
            },
            None,
        ),
        (
            {
                "eval_count": 10,
            },
            None,
        ),
    ]
    + [
        (
            {
                "prompt_eval_count": 10,
                "eval_count": 5,
                field: value,
            },
            None,
        )
        for field in (
            "prompt_eval_count",
            "eval_count",
        )
        for value in (
            -1,
            1.5,
            "10",
            True,
        )
    ],
)
def test_ollama_optional_usage(
    counts: dict,
    expected: LLMTokenUsage | None,
) -> None:
    async def run_test() -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "message": {
                        "content": " result ",
                    },
                    **counts,
                },
            )
        )

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider(
                "http://unused.test",
                "test-model",
                1,
                client,
            )

            generation = await provider.generate(
                "system",
                "user",
            )

            assert generation.text == " result "
            assert generation.usage == expected

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "response_data",
    [
        {
            "done": True,
        },
        {
            "message": {
                "content": "",
            },
        },
        {
            "message": {
                "content": "   ",
            },
        },
    ],
    ids=[
        "missing-content",
        "empty-content",
        "whitespace-content",
    ],
)
def test_ollama_provider_rejects_invalid_response(
    response_data: dict,
) -> None:
    async def run_test() -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=response_data,
            )
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
                await provider.generate(
                    "system",
                    "user",
                )

    asyncio.run(run_test())


def test_ollama_provider_sends_structured_output_schema() -> None:
    async def run_test() -> None:
        response_schema = {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                },
            },
            "required": [
                "title",
            ],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)

            assert request.url.path == "/api/chat"
            assert payload["model"] == "qwen3:4b"
            assert payload["stream"] is False
            assert payload["think"] is False

            assert payload["format"] == response_schema
            assert payload["options"]["num_predict"] == 500
            assert payload["options"]["temperature"] == 0

            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": '{"title":"Sprint Tasks"}',
                    },
                },
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

            result = await provider.generate(
                system_prompt="system",
                user_prompt="user",
                max_new_tokens=500,
                response_schema=response_schema,
            )

            assert result.text == '{"title":"Sprint Tasks"}'
            assert result.usage is None

    asyncio.run(run_test())