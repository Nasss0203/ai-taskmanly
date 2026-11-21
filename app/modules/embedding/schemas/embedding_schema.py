from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.shared.request_limits import require_non_blank

# M5 (kế hoạch hạ tầng vector, F6): NestJS batches the texts of a Page.
MAX_EMBEDDING_TEXTS = 32
MAX_EMBEDDING_TEXT_LENGTH = 2000
# Keeps the body under the request limit even for Vietnamese text.
MAX_EMBEDDING_TOTAL_LENGTH = 16000

EmbeddingText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_EMBEDDING_TEXT_LENGTH),
    AfterValidator(require_non_blank),
]


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A search sentence gets the model's query instruction; Page text does not.
    kind: Literal["query", "document"]
    texts: list[EmbeddingText] = Field(min_length=1, max_length=MAX_EMBEDDING_TEXTS)

    @model_validator(mode="after")
    def validate_total_length(self) -> "EmbeddingRequest":
        if sum(len(text) for text in self.texts) > MAX_EMBEDDING_TOTAL_LENGTH:
            raise ValueError("Texts exceed the 16000-character total.")
        return self


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    dimensions: int
    # Unit length: cosine similarity is the dot product.
    embeddings: list[list[float]]
