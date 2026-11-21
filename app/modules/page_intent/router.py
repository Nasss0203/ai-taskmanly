from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

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
    response = await service.process(request)
    # M8: "basedOn" is written into "result" by the response's own serializer,
    # which FastAPI's re-validation against the result models would reject.
    return JSONResponse(response.model_dump(mode="json"))
