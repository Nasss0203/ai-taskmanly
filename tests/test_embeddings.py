import asyncio
import json
import math

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import InvalidLLMResponseError, LLMProviderError
from app.llm.base import EmbeddingResult
from app.llm.providers.ollama_embedding import OllamaEmbeddingProvider
from app.main import app
from app.modules.embedding.services.embedding_service import (
    QUERY_INSTRUCTION,
    EmbeddingService,
)

TEST_TOKEN = "test-internal-service-token"
HEADERS = {"X-Internal-Service-Token": TEST_TOKEN}


class RecordingEmbeddingProvider:
    provider_name = "fake"

    def __init__(self, model_name="qwen3-embedding:0.6b", vectors=None):
        self.model_name = model_name
        self.vectors = vectors
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(texts)
        vectors = self.vectors or [[3.0, 4.0] for _ in texts]
        return EmbeddingResult(embeddings=vectors, model=self.model_name)

    async def close(self):
        return None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with TestClient(app) as test_client:
        yield test_client


def use(client, provider):
    client.app.state.embedding_service = EmbeddingService(provider)
    return provider


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Service-Token": "bad"}])
def test_requires_internal_token(client, headers):
    response = client.post(
        "/internal/v1/embeddings",
        headers=headers,
        json={"kind": "document", "texts": ["a"]},
    )
    assert response.status_code == 401


def test_returns_one_unit_vector_per_text(client):
    provider = use(client, RecordingEmbeddingProvider())
    response = client.post(
        "/internal/v1/embeddings",
        headers=HEADERS,
        json={"kind": "document", "texts": ["Kế hoạch phát hành", "Họp tuần"]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "model": "qwen3-embedding:0.6b",
        "dimensions": 2,
        "embeddings": [[0.6, 0.8], [0.6, 0.8]],
    }
    # Page text is embedded as it is.
    assert provider.calls == [["Kế hoạch phát hành", "Họp tuần"]]


def test_query_gets_the_instruction_only_for_qwen3_embedding(client):
    provider = use(client, RecordingEmbeddingProvider())
    client.post(
        "/internal/v1/embeddings",
        headers=HEADERS,
        json={"kind": "query", "texts": ["trang nói về OAuth"]},
    )
    assert provider.calls == [[f"{QUERY_INSTRUCTION}trang nói về OAuth"]]

    provider = use(client, RecordingEmbeddingProvider(model_name="bge-m3"))
    client.post(
        "/internal/v1/embeddings",
        headers=HEADERS,
        json={"kind": "query", "texts": ["trang nói về OAuth"]},
    )
    assert provider.calls == [["trang nói về OAuth"]]


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "document", "texts": []},
        {"kind": "document", "texts": ["   "]},
        {"kind": "document", "texts": ["a"] * 33},
        {"kind": "document", "texts": ["a" * 2001]},
        {"kind": "document", "texts": ["a" * 2000] * 9},
        {"kind": "summary", "texts": ["a"]},
        {"kind": "document", "texts": ["a"], "model": "other"},
    ],
)
def test_request_validation(client, body):
    provider = use(client, RecordingEmbeddingProvider())
    response = client.post("/internal/v1/embeddings", headers=HEADERS, json=body)
    assert response.status_code == 422
    assert provider.calls == []


@pytest.mark.parametrize(
    "vectors",
    [
        [[1.0, 0.0]],  # one vector for two texts
        [[1.0, 0.0], [1.0]],  # different sizes
        [[0.0, 0.0], [1.0, 0.0]],  # zero length
        [[math.nan, 1.0], [1.0, 0.0]],
    ],
)
def test_bad_vectors_are_502(client, vectors):
    use(client, RecordingEmbeddingProvider(vectors=vectors))
    response = client.post(
        "/internal/v1/embeddings",
        headers=HEADERS,
        json={"kind": "document", "texts": ["a", "b"]},
    )
    assert response.status_code == 502


def run_provider(handler, num_gpu=0):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://ollama.test",
        ) as http_client:
            provider = OllamaEmbeddingProvider(
                "http://unused.test", "qwen3-embedding:0.6b", 5, http_client, num_gpu
            )
            return await provider.embed(["a", "b"])

    return asyncio.run(run())


def test_ollama_provider_calls_embed_on_the_cpu():
    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == "/api/embed"
        assert payload == {
            "model": "qwen3-embedding:0.6b",
            "input": ["a", "b"],
            "truncate": True,
            "options": {"num_gpu": 0},
        }
        return httpx.Response(200, json={"embeddings": [[1, 0], [0, 1]]})

    assert run_provider(handler) == EmbeddingResult(
        embeddings=[[1.0, 0.0], [0.0, 1.0]], model="qwen3-embedding:0.6b"
    )


def test_ollama_provider_lets_ollama_pick_without_num_gpu():
    def handler(request):
        assert "options" not in json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[1], [1]]})

    run_provider(handler, num_gpu=None)


@pytest.mark.parametrize(
    "body",
    [
        {"embeddings": [[1, 0]]},
        {"embeddings": [[1, 0], [1]]},
        {"embeddings": [[1, True], [0, 1]]},
        {"embeddings": [[1, "x"], [0, 1]]},
        {"error": "model not found"},
    ],
)
def test_ollama_provider_rejects_bad_responses(body):
    with pytest.raises(InvalidLLMResponseError):
        run_provider(lambda request: httpx.Response(200, json=body))


def test_ollama_error_body_never_reaches_logs(caplog):
    private = "SENSITIVE_UPSTREAM_ERROR_FIXTURE_52817"
    with caplog.at_level("INFO"), pytest.raises(LLMProviderError):
        run_provider(lambda request: httpx.Response(500, text=private))
    assert private not in caplog.text
    assert "reason=http_500" in caplog.text
