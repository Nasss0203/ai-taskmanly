from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from app.api.internal.v1.router import router as internal_router
from app.api.v1.router import router
from app.api.request_limits import AIRequestLimitsMiddleware
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.llm.base import LLMProvider
from app.llm.factory import create_embedding_provider, create_gemini_provider, create_llm_provider
from app.llm.providers.fallback import FallbackLLMProvider
from app.modules.embedding.services.embedding_service import EmbeddingService
from app.modules.intent.services.intent_service import IntentService
from app.modules.modification_planner.services.modification_planner_service import (
    ModificationPlannerService,
)
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_composition.services import PageCompositionService
from app.modules.page_question.service import PageQuestionService
from app.modules.writing.services import WritingService


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    async with AsyncExitStack() as exit_stack:
        def num_gpu_for(model_name: str, requested: int | None) -> int | None:
            # OLLAMA_MODEL_NUM_GPU gives each model one placement, so every
            # job calling it shares the same loaded copy.
            return settings.ollama_model_num_gpu.get(model_name, requested)

        default_num_gpu = num_gpu_for(settings.ollama_model, settings.ollama_num_gpu)
        provider = create_llm_provider(
            settings.model_copy(update={"ollama_num_gpu": default_num_gpu})
        )

        exit_stack.push_async_callback(provider.close)

        providers_by_config: dict[
            tuple[str, int | None],
            LLMProvider,
        ] = {}

        if settings.llm_provider == "ollama":
            providers_by_config[
                (
                    settings.ollama_model,
                    default_num_gpu,
                )
            ] = provider

        def get_or_create_ollama_provider(
            model_name: str,
            num_gpu: int | None,
        ) -> LLMProvider:
            num_gpu = num_gpu_for(model_name, num_gpu)
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

        gemini_providers: list[LLMProvider] = []

        def for_task(choice: str | None, current: LLMProvider | None) -> LLMProvider | None:
            if choice != "gemini":
                return current
            if not gemini_providers:
                gemini_providers.append(create_gemini_provider(settings))
                exit_stack.push_async_callback(gemini_providers[0].close)
            if not settings.llm_fallback_to_ollama or current is None:
                return gemini_providers[0]
            return FallbackLLMProvider(gemini_providers[0], current)

        ollama_writing_provider = (
            get_or_create_ollama_provider(
                settings.ollama_writing_model,
                settings.ollama_num_gpu,
            )
            if settings.llm_provider == "ollama" and settings.ollama_writing_model
            else provider
        )
        if settings.continue_llm_provider == "gemini":
            continue_provider = for_task("gemini", continue_provider or ollama_writing_provider)
        page_composition_provider = for_task(settings.page_composition_llm_provider, page_composition_provider)
        modification_planner_provider = for_task(
            settings.modification_planner_llm_provider, modification_planner_provider
        )
        writing_provider = for_task(settings.writing_llm_provider, ollama_writing_provider)
        question_provider = (
            ollama_writing_provider
            if settings.page_question_llm_provider == "ollama"
            else for_task("gemini", ollama_writing_provider)
            if settings.page_question_llm_provider == "gemini"
            else writing_provider
        )
        application.state.writing_service = WritingService(
            writing_provider,
            continue_provider,
        )
        application.state.page_question_service = PageQuestionService(question_provider)

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
        # Kế hoạch tốc độ Ask (A.2): page-intent on the default CPU copy took
        # ~71% of an Ask. OLLAMA_INTENT_MODEL moves intent and page-intent to
        # another model; its placement still comes from OLLAMA_MODEL_NUM_GPU,
        # so naming the planner's model shares its loaded copy.
        intent_provider = provider
        if (
            settings.llm_provider == "ollama"
            and settings.ollama_intent_model
            and settings.ollama_intent_model != settings.ollama_model
        ):
            intent_provider = get_or_create_ollama_provider(
                settings.ollama_intent_model,
                settings.ollama_num_gpu,
            )
        application.state.page_intent_service = PageIntentService(intent_provider)
        application.state.intent_service = IntentService(intent_provider)

        embedding_provider = create_embedding_provider(settings)
        exit_stack.push_async_callback(embedding_provider.close)
        application.state.embedding_service = EmbeddingService(
            embedding_provider
        )

        yield


app = FastAPI(
    title="Taskmanly AI Service",
    version="1.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)
app.add_middleware(AIRequestLimitsMiddleware)

app.include_router(
    router,
    prefix="/api/v1",
)

app.include_router(
    internal_router,
    prefix="/internal/v1",
)
