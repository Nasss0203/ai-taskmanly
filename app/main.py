from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.internal.v1.router import router as internal_router
from app.api.v1.router import router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.llm.factory import create_llm_provider
from app.modules.page_composition.services import PageCompositionService
from app.modules.writing.services import WritingService


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    provider = create_llm_provider(settings)

    continue_provider = None
    page_composition_provider = provider

    try:
        if (
            settings.llm_provider == "ollama"
            and settings.ollama_continue_model
            and settings.ollama_continue_model != settings.ollama_model
        ):
            continue_settings = settings.model_copy(
                update={
                    "ollama_model": settings.ollama_continue_model,
                }
            )

            continue_provider = create_llm_provider(
                continue_settings
            )

        if (
            settings.llm_provider == "ollama"
            and settings.ollama_page_composition_model
        ):
            page_model = (
                settings.ollama_page_composition_model
            )

            if page_model == settings.ollama_model:
                page_composition_provider = provider

            elif (
                continue_provider is not None
                and page_model == settings.ollama_continue_model
            ):
                page_composition_provider = continue_provider

            else:
                page_settings = settings.model_copy(
                    update={
                        "ollama_model": page_model,
                    }
                )

                page_composition_provider = (
                    create_llm_provider(
                        page_settings
                    )
                )

        application.state.settings = settings

        application.state.writing_service = WritingService(
            provider,
            continue_provider,
        )

        application.state.page_composition_service = (
            PageCompositionService(
                page_composition_provider
            )
        )

        yield

    finally:
        if (
            page_composition_provider is not provider
            and page_composition_provider is not continue_provider
        ):
            await page_composition_provider.close()

        if (
            continue_provider is not None
            and continue_provider is not provider
        ):
            await continue_provider.close()

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