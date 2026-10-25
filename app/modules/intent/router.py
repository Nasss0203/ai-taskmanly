from fastapi import APIRouter, Depends

from app.api.dependencies import get_intent_service
from app.modules.intent.schemas.intent_schema import IntentRequest, IntentResponse
from app.modules.intent.services.intent_service import IntentService


router = APIRouter()


@router.post('', response_model=IntentResponse)
async def classify_intent(
    request: IntentRequest,
    service: IntentService = Depends(get_intent_service),
) -> IntentResponse:
    return await service.process(request)
