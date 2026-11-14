import asyncio
import json

import httpx
import pytest

from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.llm.base import LLMTokenUsage
from app.llm.providers.gemini import GeminiProvider

KEY = "TEST_GEMINI_KEY_FIXTURE_80431"
PRIVATE = "SENSITIVE_UPSTREAM_ERROR_FIXTURE_51927"
PROMPT = "PRIVATE_PROMPT_FIXTURE_33018"
OK_BODY = {
    "candidates": [{"content": {"parts": [{"text": " xin chào "}]}, "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 3, "totalTokenCount": 18},
}


def run(handler, *, sleeps=None, **options):
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="https://gemini.test/v1beta") as client:
            async def sleep(seconds):
                if sleeps is not None:
                    sleeps.append(seconds)

            provider = GeminiProvider(api_key=KEY, model_name="gemini-test", timeout_seconds=5,
                                      client=client, sleep=sleep, **options)
            return await provider.generate("system rules", PROMPT, max_new_tokens=300)

    return asyncio.run(call())


def run_with_schema(handler, schema):
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="https://gemini.test/v1beta") as client:
            provider = GeminiProvider(api_key=KEY, model_name="gemini-test", timeout_seconds=5, client=client)
            return await provider.generate("system rules", PROMPT, max_new_tokens=200, response_schema=schema)

    return asyncio.run(call())


def test_calls_generate_content_with_the_key_in_a_header() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    result = run(handler)
    request, body = seen["request"], seen["body"]
    assert request.method == "POST"
    assert request.url.path == "/v1beta/models/gemini-test:generateContent"
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url)
    assert body["systemInstruction"] == {"parts": [{"text": "system rules"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": PROMPT}]}]
    config = body["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingLevel": "MINIMAL"}
    assert config["maxOutputTokens"] == 300 + 1024
    assert "responseJsonSchema" not in config
    assert "temperature" not in config
    assert result.text == " xin chào "
    assert result.usage == LLMTokenUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18)


def test_structured_output_sends_the_schema_and_temperature_zero() -> None:
    schema = {"type": "object", "properties": {"intent": {"type": "string"}}, "required": ["intent"],
              "additionalProperties": False}
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["config"] = json.loads(request.content)["generationConfig"]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"intent":"OTHER"}'}]}}]})

    result = run_with_schema(handler, schema)
    assert seen["config"]["responseMimeType"] == "application/json"
    assert seen["config"]["responseJsonSchema"] == schema
    assert seen["config"]["temperature"] == 0
    assert result.text == '{"intent":"OTHER"}'
    assert result.usage is None


def test_without_a_thinking_level_the_output_limit_is_the_callers() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["config"] = json.loads(request.content)["generationConfig"]
        return httpx.Response(200, json=OK_BODY)

    run(handler, thinking_level=None)
    assert "thinkingConfig" not in seen["config"]
    assert seen["config"]["maxOutputTokens"] == 300


def test_text_parts_are_joined_and_thoughts_skipped() -> None:
    body = {"candidates": [{"content": {"parts": [{"text": "suy nghĩ", "thought": True}, {"text": "Một "},
                                                  {"text": "hai"}]}}]}
    assert run(lambda request: httpx.Response(200, json=body)).text == "Một hai"


def test_text_cut_by_the_token_limit_is_still_returned() -> None:
    body = {"candidates": [{"content": {"parts": [{"text": "dở dang"}]}, "finishReason": "MAX_TOKENS"}]}
    assert run(lambda request: httpx.Response(200, json=body)).text == "dở dang"


@pytest.mark.parametrize(("headers", "body", "wait"), [
    ({"Retry-After": "7"}, {}, 7.0),
    ({}, {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "3s"}]}}, 3.0),
    ({}, {}, 1.0),
])
def test_rate_limit_waits_and_retries(headers, body, wait) -> None:
    replies = [httpx.Response(429, headers=headers, json=body), httpx.Response(200, json=OK_BODY)]
    sleeps = []
    result = run(lambda request: replies.pop(0), sleeps=sleeps)
    assert result.text == " xin chào "
    assert sleeps == [wait]


def test_rate_limit_wait_is_capped() -> None:
    replies = [httpx.Response(429, headers={"Retry-After": "3600"}), httpx.Response(200, json=OK_BODY)]
    sleeps = []
    run(lambda request: replies.pop(0), sleeps=sleeps)
    assert sleeps == [60.0]


def test_rate_limit_after_the_last_retry_is_unavailable() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, text=PRIVATE)

    with pytest.raises(LLMUnavailableError):
        run(handler, sleeps=[], max_retries=2)
    assert len(calls) == 3


@pytest.mark.parametrize(("status", "error", "calls"), [
    (500, LLMUnavailableError, 1), (503, LLMUnavailableError, 3),
    (400, LLMProviderError, 1), (403, LLMProviderError, 1),
])
def test_http_errors(status, error, calls) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, text=PRIVATE)

    with pytest.raises(error) as raised:
        run(handler, sleeps=[])
    assert len(seen) == calls
    if error is LLMProviderError:
        assert not isinstance(raised.value, (LLMUnavailableError, InvalidLLMResponseError))


def test_timeout_is_not_retried() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMTimeoutError):
        run(handler, sleeps=[])
    assert len(seen) == 1


def test_connection_error_after_the_last_retry_is_unavailable() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(LLMUnavailableError):
        run(handler, sleeps=[])
    assert len(seen) == 3


def test_overloaded_server_waits_and_retries() -> None:
    replies = [httpx.Response(503, text=PRIVATE), httpx.Response(503, headers={"Retry-After": "2"}),
               httpx.Response(200, json=OK_BODY)]
    sleeps = []
    assert run(lambda request: replies.pop(0), sleeps=sleeps).text == " xin chào "
    assert sleeps == [5.0, 2.0]


def test_lost_connection_waits_and_retries() -> None:
    replies = ["down", httpx.Response(200, json=OK_BODY)]

    def handler(request: httpx.Request) -> httpx.Response:
        reply = replies.pop(0)
        if reply == "down":
            raise httpx.ConnectError("down", request=request)
        return reply

    sleeps = []
    assert run(handler, sleeps=sleeps).text == " xin chào "
    assert sleeps == [5.0]


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
    httpx.Response(200, json={"candidates": []}),
    httpx.Response(200, json={"candidates": [{"finishReason": "SAFETY"}]}),
    httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "   "}]}}]}),
    httpx.Response(200, json={"candidates": "wrong"}),
    httpx.Response(200, json=["wrong"]),
    httpx.Response(200, text="not json"),
], ids=["blocked", "no-candidates", "no-content", "blank", "candidates-not-list", "not-object", "not-json"])
def test_responses_without_text_are_invalid(response) -> None:
    with pytest.raises(InvalidLLMResponseError):
        run(lambda request: response)


@pytest.mark.parametrize("response", [
    httpx.Response(400, text=PRIVATE), httpx.Response(429, text=PRIVATE), httpx.Response(500, text=PRIVATE),
    httpx.Response(200, json={"promptFeedback": {"blockReason": PRIVATE}}),
    httpx.Response(200, json=OK_BODY),
])
def test_logs_never_hold_the_key_the_prompt_or_the_api_body(caplog, response) -> None:
    with caplog.at_level("INFO"):
        try:
            run(lambda request: response, sleeps=[])
        except LLMProviderError:
            pass
    assert "provider=gemini model=gemini-test" in caplog.text
    for secret in (KEY, PRIVATE, PROMPT):
        assert secret not in caplog.text


def test_close_only_closes_its_own_client() -> None:
    async def call():
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=OK_BODY)))
        shared = GeminiProvider(api_key=KEY, model_name="gemini-test", timeout_seconds=5, client=client)
        await shared.close()
        assert not client.is_closed
        await client.aclose()
        owned = GeminiProvider(api_key=KEY, model_name="gemini-test", timeout_seconds=5)
        await owned.close()
        assert owned._client.is_closed

    asyncio.run(call())
