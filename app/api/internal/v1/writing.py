from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_writing_service
from app.modules.writing.schemas import WritingRequest, WritingResponse
from app.modules.writing.service import WritingService


router = APIRouter()


@router.post("", response_model=WritingResponse)
async def write(
    request: WritingRequest,
    service: Annotated[WritingService, Depends(get_writing_service)],
) -> WritingResponse:
    return await service.write(request)
