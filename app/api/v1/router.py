from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.modules.assistant.router import router as assistant_router

router = APIRouter()

router.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)

router.include_router(
    assistant_router,
    prefix="/assistant",
    tags=["AI Assistant"],
)
