from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_page_composition_service
from app.modules.page_composition.schemas.page_composition_schema import (
    PageCompositionRequest,
    PageCompositionResponse,
)
from app.modules.page_composition.services import PageCompositionService


router = APIRouter()


@router.post(
    "",
    response_model=PageCompositionResponse,
    response_model_exclude_none=True,
)
async def generate_page_composition(
    request: PageCompositionRequest,
    service: Annotated[
        PageCompositionService,
        Depends(get_page_composition_service),
    ],
) -> PageCompositionResponse:
    return await service.process(request)