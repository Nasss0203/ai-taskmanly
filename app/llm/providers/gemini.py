import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

import httpx

from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.llm.base import LLMGenerationResult, LLMTokenUsage

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_RATE_LIMIT_WAIT_SECONDS = 60.0
TRANSIENT_WAIT_SECONDS = 5.0


class _RateLimited(Exception):
    def __init__(self, wait_seconds: float, reason: str = "rate_limited") -> None:
        super().__init__(reason)
        self.wait_seconds = wait_seconds
        self.reason = reason


class GeminiProvider:
    provider_name = "gemini"

    def __init__(
        self,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        thinking_level: str | None = "MINIMAL",
        thinking_tokens: int = 1024,
        max_retries: int = 2,
        retry_on_rate_limit: bool = True,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.model_name = model_name
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._thinking_level = thinking_level
        self._thinking_tokens = thinking_tokens
        self._max_retries = max_retries
        self.retry_on_rate_limit = retry_on_rate_limit
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        started_at = perf_counter()
        logger.info(
            "llm_request_payload provider=%s model=%s system_chars=%d user_chars=%d "
            "max_new_tokens=%d thinking_level=%s structured=%s",
            self.provider_name, self.model_name, len(system_prompt), len(user_prompt),
            max_new_tokens, self._thinking_level or "-", response_schema is not None,
        )
        payload = self._payload(system_prompt, user_prompt, max_new_tokens, response_schema)

        attempt = 0
        while True:
            try:
                try:
                    data = await asyncio.wait_for(self._post(payload), timeout=self._timeout_seconds)
                except httpx.TimeoutException:
                    raise
                except httpx.RequestError:
                    raise _RateLimited(TRANSIENT_WAIT_SECONDS, "connection") from None
                break
            except _RateLimited as limited:
                if not self.retry_on_rate_limit or attempt >= self._max_retries:
                    self._log_failure(started_at, limited.reason)
                    if limited.reason == "connection":
                        raise LLMUnavailableError("Cannot connect to Gemini.") from None
                    if limited.reason == "http_503":
                        raise LLMUnavailableError("Gemini is unavailable.") from None
                    raise LLMUnavailableError("Gemini rate limit reached.") from None
                attempt += 1
                logger.warning("llm_retry provider=%s model=%s reason=%s attempt=%d wait_s=%.1f",
                               self.provider_name, self.model_name, limited.reason, attempt, limited.wait_seconds)
                await self._sleep(limited.wait_seconds)
            except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                self._log_failure(started_at, "timeout")
                raise LLMTimeoutError("Gemini request timed out.") from exc
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                self._log_failure(started_at, f"http_{status}")
                if status >= 500:
                    raise LLMUnavailableError("Gemini is unavailable.") from exc
                raise LLMProviderError("Gemini rejected the request.") from exc
            except httpx.RequestError as exc:
                self._log_failure(started_at, "connection")
                raise LLMUnavailableError("Cannot connect to Gemini.") from exc
            except (ValueError, KeyError, TypeError) as exc:
                self._log_failure(started_at, "invalid_response")
                raise InvalidLLMResponseError("Gemini response is not valid JSON.") from exc

        try:
            text, finish_reason = self._text(data)
        except (KeyError, TypeError, AttributeError) as exc:
            self._log_failure(started_at, "invalid_response")
            raise InvalidLLMResponseError("Gemini response does not contain text.") from exc
        if not text.strip():
            self._log_failure(started_at, "empty_response")
            raise InvalidLLMResponseError("Gemini response content is empty.")

        usage, thoughts = self._usage(data)
        logger.info(
            "llm_request_succeeded provider=%s model=%s latency_ms=%.2f prompt_tokens=%s "
            "completion_tokens=%s thought_tokens=%s finish_reason=%s retries=%d",
            self.provider_name, self.model_name, (perf_counter() - started_at) * 1000,
            usage.prompt_tokens if usage else "-", usage.completion_tokens if usage else "-",
            thoughts if thoughts is not None else "-", finish_reason, attempt,
        )
        return LLMGenerationResult(text=text, usage=usage)

    def _payload(self, system_prompt: str, user_prompt: str, max_new_tokens: int,
                 response_schema: dict[str, Any] | None) -> dict[str, Any]:
        config: dict[str, Any] = {"maxOutputTokens": max_new_tokens}
        if self._thinking_level:
            config["thinkingConfig"] = {"thinkingLevel": self._thinking_level}
            config["maxOutputTokens"] = max_new_tokens + self._thinking_tokens
        if response_schema is not None:
            config["responseMimeType"] = "application/json"
            config["responseJsonSchema"] = response_schema
            config["temperature"] = 0
        return {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": config,
        }

    async def _post(self, payload: dict[str, Any]) -> Any:
        response = await self._client.post(
            f"/models/{self.model_name}:generateContent",
            json=payload,
            headers={"x-goog-api-key": self._api_key},
        )
        if response.status_code == 429:
            raise _RateLimited(self._wait_seconds(response))
        if response.status_code == 503:
            header = response.headers.get("Retry-After", "").strip()
            wait = float(header) if header.replace(".", "", 1).isdigit() else TRANSIENT_WAIT_SECONDS
            raise _RateLimited(min(wait, MAX_RATE_LIMIT_WAIT_SECONDS), "http_503")
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _wait_seconds(response: httpx.Response) -> float:
        wait = 1.0
        header = response.headers.get("Retry-After")
        if header and header.strip().replace(".", "", 1).isdigit():
            wait = float(header)
        else:
            try:
                details = response.json()["error"]["details"]
                delays = [item["retryDelay"] for item in details if isinstance(item, dict) and "retryDelay" in item]
                if delays and str(delays[0]).endswith("s"):
                    wait = float(str(delays[0])[:-1])
            except (ValueError, KeyError, TypeError):
                pass
        return min(max(wait, 0.0), MAX_RATE_LIMIT_WAIT_SECONDS)

    @staticmethod
    def _text(data: Any) -> tuple[str, str]:
        if not isinstance(data, dict):
            raise TypeError("Gemini response is not an object.")
        if (data.get("promptFeedback") or {}).get("blockReason"):
            return "", "BLOCKED"
        candidates = data.get("candidates")
        if candidates is None:
            return "", "-"
        if not isinstance(candidates, list):
            raise TypeError("Gemini candidates is not a list.")
        if not candidates:
            return "", "-"
        candidate = candidates[0]
        reason = candidate.get("finishReason")
        finish_reason = reason if isinstance(reason, str) and reason.replace("_", "").isalnum() else "-"
        parts = (candidate.get("content") or {}).get("parts") or []
        pieces = []
        for part in parts:
            if part.get("thought"):
                continue
            piece = part.get("text")
            if piece is not None and not isinstance(piece, str):
                raise TypeError("Gemini part text is not text.")
            pieces.append(piece or "")
        return "".join(pieces), finish_reason

    @staticmethod
    def _usage(data: dict[str, Any]) -> tuple[LLMTokenUsage | None, int | None]:
        metadata = data.get("usageMetadata")
        if not isinstance(metadata, dict):
            return None, None

        def count(key: str) -> int | None:
            value = metadata.get(key)
            return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

        prompt, answer, thoughts = count("promptTokenCount"), count("candidatesTokenCount"), count("thoughtsTokenCount")
        if prompt is None or answer is None:
            return None, thoughts
        completion = answer + (thoughts or 0)
        total = count("totalTokenCount")
        return LLMTokenUsage(prompt_tokens=prompt, completion_tokens=completion,
                             total_tokens=total if total is not None else prompt + completion), thoughts

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _log_failure(self, started_at: float, reason: str) -> None:
        logger.warning(
            "llm_request_failed provider=%s model=%s reason=%s latency_ms=%.2f",
            self.provider_name, self.model_name, reason, (perf_counter() - started_at) * 1000,
        )
