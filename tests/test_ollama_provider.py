import asyncio
import json

import httpx
import pytest

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMTokenUsage
from app.llm.providers.ollama import OllamaProvider


@pytest.mark.parametrize("status", [400, 500])
def test_ollama_error_body_never_reaches_logs(caplog, status):
    from app.core.exceptions import LLMProviderError

    private = "SENSITIVE_UPSTREAM_ERROR_FIXTURE_49371"

    async def run_test():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, text=private)),
            base_url="http://ollama.test",
        ) as client:
            provider = OllamaProvider("http://unused.test", "test-model", 1, client)
            with pytest.raises(LLMProviderError):
                await provider.generate("system", private)

    with caplog.at_level("INFO"):
        asyncio.run(run_test())
    assert private not in caplog.text
    assert f"status={status}" in caplog.text
    assert "provider=ollama model=test-model" in caplog.text


def test_ollama_provider_calls_chat_api() -> None:
    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)

            assert request.url.path == "/api/chat"
            assert payload["model"] == "qwen3:4b"
            assert payload["stream"] is True
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
            assert payload["stream"] is True
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

class SlowStream(httpx.AsyncByteStream):
    """Ollama stream lines, with a pause before each one."""

    def __init__(self, lines: list[dict], pause: float = 0) -> None:
        self.lines = lines
        self.pause = pause

    async def __aiter__(self):
        for line in self.lines:
            await asyncio.sleep(self.pause)
            yield (json.dumps(line) + "\n").encode()


def stream_provider(stream: httpx.AsyncByteStream, timeout_seconds: float = 1):
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
        base_url="http://ollama.test",
    )
    return client, OllamaProvider("http://unused.test", "test-model", timeout_seconds, client)


def test_ollama_joins_streamed_lines_and_reads_usage_from_the_last() -> None:
    lines = [
        {"message": {"content": '{"a":'}, "done": False},
        {"message": {"content": " 1}"}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 7, "eval_count": 3},
    ]

    async def run_test() -> None:
        client, provider = stream_provider(SlowStream(lines))
        async with client:
            generation = await provider.generate("system", "user")
        assert generation.text == '{"a": 1}'
        assert generation.usage == LLMTokenUsage(7, 3, 10)

    asyncio.run(run_test())


def test_ollama_stream_error_line_is_a_provider_error_and_never_logged(caplog) -> None:
    from app.core.exceptions import LLMProviderError

    private = "SENSITIVE_STREAM_ERROR_FIXTURE_81624"
    lines = [{"message": {"content": "partial"}, "done": False}, {"error": private}]

    async def run_test() -> None:
        client, provider = stream_provider(SlowStream(lines))
        async with client:
            with pytest.raises(LLMProviderError):
                await provider.generate("system", "user")

    with caplog.at_level("INFO"):
        asyncio.run(run_test())
    assert private not in caplog.text
    assert "reason=stream_error" in caplog.text


def test_ollama_total_timeout_caps_a_reply_that_keeps_streaming() -> None:
    from app.core.exceptions import LLMTimeoutError

    # Every line arrives quickly, but the whole reply takes too long.
    lines = [{"message": {"content": "x"}, "done": False}] * 20

    async def run_test() -> None:
        client, provider = stream_provider(SlowStream(lines, pause=0.02), timeout_seconds=0.1)
        async with client:
            with pytest.raises(LLMTimeoutError):
                await provider.generate("system", "user")

    asyncio.run(run_test())


def test_ollama_idle_timeout_never_exceeds_the_total_timeout() -> None:
    async def run_test() -> None:
        provider = OllamaProvider("http://ollama.test", "m", 30, idle_timeout_seconds=60)
        assert provider._client.timeout.read == 30
        await provider.close()
        provider = OllamaProvider("http://ollama.test", "m", 300, idle_timeout_seconds=60)
        assert provider._client.timeout.read == 60
        await provider.close()

    asyncio.run(run_test())


def test_ollama_success_log_has_token_and_timing_breakdown(caplog) -> None:
    # Kế hoạch tạo trang + rút gọn ngữ cảnh (bước chung): prompt reading vs generation.
    async def run_test() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            "message": {"content": "private-output"}, "done_reason": "stop",
            "prompt_eval_count": 1320, "eval_count": 75,
            "prompt_eval_duration": 410_000_000, "eval_duration": 2_600_000_000, "load_duration": 15_000_000,
        }))
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama.test") as client:
            await OllamaProvider("http://unused.test", "test-model", 1, client).generate("system", "private-user")

    with caplog.at_level("INFO"):
        asyncio.run(run_test())
    assert "prompt_tokens=1320 completion_tokens=75 prompt_ms=410 generate_ms=2600 load_ms=15 done_reason=stop" in caplog.text
    assert "private" not in caplog.text


def test_ollama_success_log_tolerates_missing_timing(caplog) -> None:
    async def run_test() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"message": {"content": "x"}}))
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama.test") as client:
            await OllamaProvider("http://unused.test", "test-model", 1, client).generate("system", "user")

    with caplog.at_level("INFO"):
        asyncio.run(run_test())
    assert "prompt_tokens=- completion_tokens=- prompt_ms=- generate_ms=- load_ms=- done_reason=-" in caplog.text
