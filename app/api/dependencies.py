from secrets import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.modules.modification_planner.services.modification_planner_service import (
    ModificationPlannerService,
)
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_composition.services import PageCompositionService
from app.modules.writing.services import WritingService


async def require_internal_service_token(
    request: Request,
    token: Annotated[
        str | None,
        Header(alias="X-Internal-Service-Token"),
    ] = None,
) -> None:
    expected = (
        request.app.state.settings.ai_internal_token.get_secret_value()
    )

    if token is None or not compare_digest(
        token.encode(),
        expected.encode(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service token.",
        )


def get_writing_service(
    request: Request,
) -> WritingService:
    return request.app.state.writing_service


def get_page_composition_service(
    request: Request,
) -> PageCompositionService:
    return request.app.state.page_composition_service


def get_modification_planner_service(
    request: Request,
) -> ModificationPlannerService:
    return request.app.state.modification_planner_service


def get_page_intent_service(request: Request) -> PageIntentService:
    return request.app.state.page_intent_service
