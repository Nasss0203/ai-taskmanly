from fastapi import APIRouter, Depends

from app.api.dependencies import get_page_intent_service
from app.modules.page_intent.schemas.page_intent_schema import (
    PageIntentRequest,
    PageIntentResponse,
)
from app.modules.page_intent.services.page_intent_service import PageIntentService


router = APIRouter()


@router.post("", response_model=PageIntentResponse)
async def extract_page_intent(
    request: PageIntentRequest,
    service: PageIntentService = Depends(get_page_intent_service),
) -> PageIntentResponse:
    return await service.process(request)
