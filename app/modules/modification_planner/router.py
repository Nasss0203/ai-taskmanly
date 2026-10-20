from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_modification_planner_service
from app.modules.modification_planner.schemas.modification_planner_schema import (
    ModificationPlannerRequest,
    ModificationPlannerResponse,
)
from app.modules.modification_planner.services.modification_planner_service import (
    ModificationPlannerService,
)


router = APIRouter()


@router.post(
    "",
    response_model=ModificationPlannerResponse,
    response_model_exclude_unset=True,
)
async def generate_modification_plan(
    request: ModificationPlannerRequest,
    service: Annotated[
        ModificationPlannerService,
        Depends(get_modification_planner_service),
    ],
) -> ModificationPlannerResponse:
    return await service.process(request)