import asyncio
import json
import logging
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


class OllamaProvider:
    provider_name = "ollama"

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
        num_ctx: int | None = None,
        num_gpu: int | None = None,
        idle_timeout_seconds: float | None = None,
    ) -> None:
        self.model_name = model_name
        self._num_ctx = num_ctx
        self._num_gpu = num_gpu

        # The reply is streamed: a long page may take minutes while tokens
        # keep coming, but a silent model fails after the idle timeout.
        # timeout_seconds still caps the whole request.
        self._timeout_seconds = timeout_seconds

        self._owns_client = client is None

        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=min(idle_timeout_seconds or timeout_seconds, timeout_seconds),
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        started_at = perf_counter()

        logger.info(
            "llm_request_started provider=%s model=%s",
            self.provider_name,
            self.model_name,
        )

        logger.info(
            "llm_request_payload "
            "provider=%s model=%s "
            "system_chars=%d user_chars=%d "
            "max_new_tokens=%d num_ctx=%s "
            "num_gpu=%s structured=%s",
            self.provider_name,
            self.model_name,
            len(system_prompt),
            len(user_prompt),
            max_new_tokens,
            self._num_ctx,
            self._num_gpu,
            response_schema is not None,
        )

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "stream": True,
            "think": False,
            "options": {
                "num_predict": max_new_tokens,
            },
        }

        if self._num_ctx is not None:
            payload["options"]["num_ctx"] = self._num_ctx

        if self._num_gpu is not None:
            payload["options"]["num_gpu"] = self._num_gpu

        if response_schema is not None:
            payload["format"] = response_schema
            payload["options"]["temperature"] = 0

        try:
            content, final = await asyncio.wait_for(
                self._stream_chat(payload),
                timeout=self._timeout_seconds,
            )

        except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
            self._log_failure(
                started_at,
                "timeout",
            )

            raise LLMTimeoutError(
                "Ollama request timed out."
            ) from exc

        except httpx.HTTPStatusError as exc:
            self._log_failure(
                started_at,
                f"http_{exc.response.status_code}",
            )

            logger.warning(
                "llm_http_error "
                "provider=%s model=%s status=%s",
                self.provider_name,
                self.model_name,
                exc.response.status_code,
            )

            if exc.response.status_code >= 500:
                raise LLMUnavailableError(
                    "Ollama is unavailable."
                ) from exc

            raise LLMProviderError(
                "Ollama rejected the request."
            ) from exc

        except httpx.RequestError as exc:
            self._log_failure(
                started_at,
                "connection",
            )

            raise LLMUnavailableError(
                "Cannot connect to Ollama."
            ) from exc

        except LLMProviderError:
            # An error line inside the stream; its text is never logged.
            self._log_failure(
                started_at,
                "stream_error",
            )

            raise

        except (ValueError, KeyError, TypeError) as exc:
            self._log_failure(
                started_at,
                "invalid_response",
            )

            raise InvalidLLMResponseError(
                "Ollama response does not contain message content."
            ) from exc

        if not content.strip():
            self._log_failure(
                started_at,
                "empty_response",
            )

            raise InvalidLLMResponseError(
                "Ollama response content is empty."
            )

        logger.info(
            "llm_request_succeeded "
            "provider=%s model=%s latency_ms=%.2f",
            self.provider_name,
            self.model_name,
            (perf_counter() - started_at) * 1000,
        )

        prompt_tokens = final.get("prompt_eval_count")
        completion_tokens = final.get("eval_count")

        usage = None

        if (
            isinstance(prompt_tokens, int)
            and not isinstance(prompt_tokens, bool)
            and prompt_tokens >= 0
            and isinstance(completion_tokens, int)
            and not isinstance(completion_tokens, bool)
            and completion_tokens >= 0
        ):
            usage = LLMTokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )

        return LLMGenerationResult(
            text=content,
            usage=usage,
        )

    async def _stream_chat(
        self,
        payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """The streamed message content and the last line (token counts)."""
        parts: list[str] = []
        final: dict[str, Any] = {}

        async with self._client.stream(
            "POST",
            "/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.strip():
                    continue

                chunk = json.loads(line)

                if not isinstance(chunk, dict):
                    raise TypeError("Ollama stream line is not an object.")

                if "error" in chunk:
                    raise LLMProviderError(
                        "Ollama reported an error while generating."
                    )

                if "message" in chunk:
                    piece = chunk["message"]["content"]

                    if not isinstance(piece, str):
                        raise TypeError("Ollama message content is not text.")

                    parts.append(piece)

                final = chunk

        if not parts:
            raise KeyError("message")

        return "".join(parts), final

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _log_failure(
        self,
        started_at: float,
        reason: str,
    ) -> None:
        logger.warning(
            "llm_request_failed "
            "provider=%s model=%s reason=%s latency_ms=%.2f",
            self.provider_name,
            self.model_name,
            reason,
            (perf_counter() - started_at) * 1000,
        )
