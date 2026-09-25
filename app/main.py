from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.internal.v1.router import router as internal_router
from app.api.v1.router import router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.llm.factory import create_llm_provider
from app.modules.writing.services import WritingService


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    provider = create_llm_provider(settings)

    application.state.settings = settings
    application.state.writing_service = WritingService(provider)
    try:
        yield
    finally:
        await provider.close()


app = FastAPI(
    title="Taskmanly AI Service",
    version="1.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(
    router,
    prefix="/api/v1",
)

app.include_router(
    internal_router,
    prefix="/internal/v1",
)
