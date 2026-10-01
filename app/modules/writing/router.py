from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_writing_service
from app.modules.writing.schemas.writing_schema import (
    WritingRequest,
    WritingResponse,
)
from app.modules.writing.services.writing_service import (
    WritingService,
)


router = APIRouter()


@router.post(
    "",
    response_model=WritingResponse,
    response_model_exclude_none=True,
)
async def writing(
    request: WritingRequest,
    service: Annotated[WritingService, Depends(get_writing_service)],
) -> WritingResponse:
    return await service.process(request)
