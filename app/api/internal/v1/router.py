from fastapi import APIRouter, Depends

from app.api.dependencies import require_internal_service_token
from app.api.internal.v1.health import router as health_router
from app.api.internal.v1.writing import router as writing_router


router = APIRouter(dependencies=[Depends(require_internal_service_token)])
router.include_router(health_router, prefix="/health", tags=["Internal Health"])
router.include_router(writing_router, prefix="/writing", tags=["AI Writing"])
