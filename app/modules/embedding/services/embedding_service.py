import math

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import EmbeddingProvider
from app.modules.embedding.schemas.embedding_schema import (
    EmbeddingRequest,
    EmbeddingResponse,
)


# Qwen3-Embedding ranks better when the search sentence says what it is for;
# Page text is embedded as it is. Other models take both as they are.
QUERY_INSTRUCTION = (
    "Instruct: Given a request from a user of a notes and tasks workspace, "
    "retrieve the page or passage it refers to\nQuery:"
)


def uses_query_instruction(model_name: str) -> bool:
    return model_name.casefold().startswith("qwen3-embedding")


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    async def process(self, request: EmbeddingRequest) -> EmbeddingResponse:
        texts = request.texts
        if request.kind == "query" and uses_query_instruction(self._provider.model_name):
            texts = [f"{QUERY_INSTRUCTION}{text}" for text in texts]

        result = await self._provider.embed(texts)
        if len(result.embeddings) != len(texts):
            raise InvalidLLMResponseError("Embedding count does not match the texts.")

        vectors = [_unit(vector) for vector in result.embeddings]
        dimensions = len(vectors[0])
        if any(len(vector) != dimensions for vector in vectors):
            raise InvalidLLMResponseError("Embeddings differ in size.")

        return EmbeddingResponse(
            model=result.model,
            dimensions=dimensions,
            embeddings=vectors,
        )


def _unit(vector: list[float]) -> list[float]:
    if not vector or not all(math.isfinite(value) for value in vector):
        raise InvalidLLMResponseError("Embedding is empty or not finite.")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise InvalidLLMResponseError("Embedding has zero length.")
    return [value / norm for value in vector]
