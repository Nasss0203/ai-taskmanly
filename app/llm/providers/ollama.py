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


logger = logging.getLogger(__name__)


class OllamaProvider:
    provider_name = "ollama"

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model_name
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
    ) -> str:
        started_at = perf_counter()
        logger.info(
            "llm_request_started provider=%s model=%s",
            self.provider_name,
            self.model_name,
        )

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "options": {"num_predict": max_new_tokens},
        }

        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            self._log_failure(started_at, "timeout")
            raise LLMTimeoutError("Ollama request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            self._log_failure(started_at, f"http_{exc.response.status_code}")
            if exc.response.status_code >= 500:
                raise LLMUnavailableError("Ollama is unavailable.") from exc
            raise LLMProviderError("Ollama rejected the request.") from exc
        except httpx.RequestError as exc:
            self._log_failure(started_at, "connection")
            raise LLMUnavailableError("Cannot connect to Ollama.") from exc

        try:
            data = response.json()
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            self._log_failure(started_at, "invalid_response")
            raise InvalidLLMResponseError(
                "Ollama response does not contain message content."
            ) from exc

        if not isinstance(content, str) or not content.strip():
            self._log_failure(started_at, "empty_response")
            raise InvalidLLMResponseError("Ollama response content is empty.")

        logger.info(
            "llm_request_succeeded provider=%s model=%s latency_ms=%.2f",
            self.provider_name,
            self.model_name,
            (perf_counter() - started_at) * 1000,
        )
        return content.strip()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _log_failure(self, started_at: float, reason: str) -> None:
        logger.warning(
            "llm_request_failed provider=%s model=%s reason=%s latency_ms=%.2f",
            self.provider_name,
            self.model_name,
            reason,
            (perf_counter() - started_at) * 1000,
        )
