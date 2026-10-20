from fastapi import APIRouter, Depends

from app.api.dependencies import require_internal_service_token
from app.api.internal.v1.health import router as health_router
from app.modules.modification_planner.router import (
    router as modification_planner_router,
)
from app.modules.page_intent.router import router as page_intent_router
from app.modules.page_composition.router import (
    router as page_composition_router,
)
from app.modules.writing.router import router as writing_router


router = APIRouter(
    dependencies=[
        Depends(require_internal_service_token),
    ],
)


router.include_router(
    health_router,
    prefix="/health",
    tags=["Internal Health"],
)

router.include_router(
    writing_router,
    prefix="/writing",
    tags=["AI Writing"],
)

router.include_router(
    page_composition_router,
    prefix="/page-composition",
    tags=["AI Page Composition"],
)

router.include_router(
    modification_planner_router,
    prefix="/modification-planner",
    tags=["AI Modification Planner"],
)

router.include_router(
    page_intent_router,
    prefix="/page-intent",
    tags=["AI Page Intent"],
)
