import asyncio
import logging
import math
from time import perf_counter
from typing import Any

import httpx

from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.llm.base import EmbeddingResult


logger = logging.getLogger(__name__)


class OllamaEmbeddingProvider:
    """Vectors from Ollama's /api/embed (M5, kế hoạch hạ tầng vector).

    Runs on the CPU unless num_gpu says otherwise, so the chat model keeps
    the GPU (F3).
    """

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
        num_gpu: int | None = None,
    ) -> None:
        self.model_name = model_name
        self._num_gpu = num_gpu
        self._timeout_seconds = timeout_seconds
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        started_at = perf_counter()
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": texts,
            "truncate": True,
        }
        if self._num_gpu is not None:
            payload["options"] = {"num_gpu": self._num_gpu}

        try:
            response = await asyncio.wait_for(
                self._client.post("/api/embed", json=payload),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
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
        except ValueError as exc:
            self._log_failure(started_at, "invalid_response")
            raise InvalidLLMResponseError(
                "Ollama response is not JSON."
            ) from exc

        embeddings = body.get("embeddings") if isinstance(body, dict) else None
        if not _is_vector_list(embeddings, len(texts)):
            self._log_failure(started_at, "invalid_response")
            raise InvalidLLMResponseError(
                "Ollama response does not contain one vector per text."
            )

        logger.info(
            "embedding_request_succeeded provider=%s model=%s texts=%d "
            "num_gpu=%s latency_ms=%.2f",
            self.provider_name,
            self.model_name,
            len(texts),
            self._num_gpu,
            (perf_counter() - started_at) * 1000,
        )
        return EmbeddingResult(
            embeddings=[[float(value) for value in vector] for vector in embeddings],
            model=self.model_name,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _log_failure(self, started_at: float, reason: str) -> None:
        logger.warning(
            "embedding_request_failed provider=%s model=%s reason=%s "
            "latency_ms=%.2f",
            self.provider_name,
            self.model_name,
            reason,
            (perf_counter() - started_at) * 1000,
        )


def _is_vector_list(value: Any, count: int) -> bool:
    if not isinstance(value, list) or len(value) != count:
        return False
    sizes = set()
    for vector in value:
        if not isinstance(vector, list) or not vector:
            return False
        for number in vector:
            if (
                isinstance(number, bool)
                or not isinstance(number, (int, float))
                or not math.isfinite(number)
            ):
                return False
        sizes.add(len(vector))
    return len(sizes) == 1
