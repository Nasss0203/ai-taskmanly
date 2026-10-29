from fastapi import APIRouter, Depends

from app.api.dependencies import get_embedding_service
from app.modules.embedding.schemas.embedding_schema import (
    EmbeddingRequest,
    EmbeddingResponse,
)
from app.modules.embedding.services.embedding_service import EmbeddingService


router = APIRouter()


@router.post("", response_model=EmbeddingResponse)
async def create_embeddings(
    request: EmbeddingRequest,
    service: EmbeddingService = Depends(get_embedding_service),
) -> EmbeddingResponse:
    return await service.process(request)
