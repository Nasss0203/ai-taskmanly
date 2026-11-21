from fastapi import APIRouter, Depends

from app.api.dependencies import require_internal_service_token
from app.modules.assistant.schemas.assistant_schema import (
    AssistantRequest,
    AssistantResponse,
)
from app.modules.assistant.services.assistant_service import assistant_service

router = APIRouter(dependencies=[Depends(require_internal_service_token)])


@router.post(
    "",
    response_model=AssistantResponse,
)
def assistant(
    request: AssistantRequest,
):
    return assistant_service.process(
        message=request.message,
        current_context=request.current_context,
    )
