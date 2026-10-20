from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from app.api.internal.v1.router import router as internal_router
from app.api.v1.router import router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.llm.base import LLMProvider
from app.llm.factory import create_llm_provider
from app.modules.modification_planner.services.modification_planner_service import (
    ModificationPlannerService,
)
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_composition.services import PageCompositionService
from app.modules.writing.services import WritingService


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    async with AsyncExitStack() as exit_stack:
        provider = create_llm_provider(settings)

        exit_stack.push_async_callback(provider.close)

        providers_by_config: dict[
            tuple[str, int | None],
            LLMProvider,
        ] = {}

        if settings.llm_provider == "ollama":
            providers_by_config[
                (
                    settings.ollama_model,
                    settings.ollama_num_gpu,
                )
            ] = provider

        def get_or_create_ollama_provider(
            model_name: str,
            num_gpu: int | None,
        ) -> LLMProvider:
            key = (model_name, num_gpu)

            existing_provider = providers_by_config.get(key)

            if existing_provider is not None:
                return existing_provider

            model_settings = settings.model_copy(
                update={
                    "ollama_model": model_name,
                    "ollama_num_gpu": num_gpu,
                }
            )

            new_provider = create_llm_provider(
                model_settings
            )

            exit_stack.push_async_callback(
                new_provider.close
            )

            providers_by_config[key] = new_provider

            return new_provider

        continue_provider = None
        page_composition_provider = provider
        modification_planner_provider = provider

        if settings.llm_provider == "ollama":

            # 1. CONTINUE provider
            if (
                settings.ollama_continue_model
                and settings.ollama_continue_model
                != settings.ollama_model
            ):
                continue_provider = get_or_create_ollama_provider(
                    settings.ollama_continue_model,
                    settings.ollama_num_gpu,
                )

            # 2. PAGE COMPOSITION provider
            if settings.ollama_page_composition_model:
                page_composition_provider = (
                    get_or_create_ollama_provider(
                        settings.ollama_page_composition_model,
                        settings.ollama_num_gpu,
                    )
                )

            # Preserve the original planner fallback:
            # use Page Composition provider when no
            # modification-specific override is configured.
            modification_planner_provider = (
                page_composition_provider
            )

            # 3. MODIFICATION PLANNER provider
            if (
                settings.ollama_modification_planner_model
                or settings.ollama_modification_planner_num_gpu
                is not None
            ):
                planner_model = (
                    settings.ollama_modification_planner_model
                    or settings.ollama_page_composition_model
                    or settings.ollama_model
                )

                planner_num_gpu = (
                    settings.ollama_modification_planner_num_gpu
                    if (
                        settings.ollama_modification_planner_num_gpu
                        is not None
                    )
                    else settings.ollama_num_gpu
                )

                modification_planner_provider = (
                    get_or_create_ollama_provider(
                        planner_model,
                        planner_num_gpu,
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

        application.state.modification_planner_service = (
            ModificationPlannerService(
                modification_planner_provider
            )
        )
        application.state.page_intent_service = PageIntentService(provider)

        yield


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
