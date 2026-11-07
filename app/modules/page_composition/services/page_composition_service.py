import logging
from time import perf_counter

from pydantic import ValidationError

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import (
    LLMGenerationResult,
    LLMProvider,
    LLMTokenUsage,
)
from app.modules.page_composition.prompts import (
    build_page_composition_prompt,
    build_page_composition_repair_prompt,
)
from app.modules.page_composition.schemas.page_composition_schema import (
    PageCompositionDraft,
    PageCompositionRequest,
    PageCompositionResponse,
    PageCompositionUsage,
)
from app.modules.modification_planner.services.sentence_normalize import normalize_create_instruction
from app.modules.page_composition.services.database_blocks import complete_databases
from app.modules.page_composition.services.task_blocks import normalize_task_blocks
from app.modules.page_composition.services.content_lock import (
    compose_explicit_page,
    drop_unrequested_databases,
    lock_composition_content,
)
from app.modules.page_composition.validators import (
    PageCompositionSemanticValidationError,
    validate_page_composition_semantics,
)
from app.shared.json_parser import parse_json_object


logger = logging.getLogger(__name__)

# A compact page (at most 8 blocks, or a 20-row table) fits well within this;
# every token costs time on a model that runs partly on the CPU.
MAX_NEW_TOKENS = 2000
EXPLICIT_PAGE_MODEL = "explicit-page-v1"


class PageCompositionService:
    def __init__(
        self,
        llm_provider: LLMProvider,
    ) -> None:
        self.llm_provider = llm_provider

    async def process(
        self,
        request: PageCompositionRequest,
    ) -> PageCompositionResponse:
        # P3 (kế hoạch sửa lỗi tạo trang): "nhờ bạn tạo giúp tôi một trang …".
        normalized = normalize_create_instruction(request.instruction)
        if normalized != request.instruction:
            request = request.model_copy(update={"instruction": normalized})
        # Kế hoạch bỏ qua model (F3): a page the sentence fully lists.
        explicit = compose_explicit_page(request.instruction)
        if explicit is not None:
            validate_page_composition_semantics(explicit)
            logger.info("page_composition_rules model=%s", EXPLICIT_PAGE_MODEL)
            return PageCompositionResponse(result=explicit, provider="rules", model=EXPLICIT_PAGE_MODEL)

        system_prompt, user_prompt = build_page_composition_prompt(
            instruction=request.instruction,
            context=request.context,
        )

        response_schema = PageCompositionDraft.model_json_schema()

        started_at = perf_counter()

        logger.info(
            "page_composition_started provider=%s model=%s",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
        )

        try:
            generation = await self.llm_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=MAX_NEW_TOKENS,
                response_schema=response_schema,
            )
        except Exception as exc:
            logger.warning(
                "page_composition_failed provider=%s model=%s "
                "error_type=%s latency_ms=%.2f",
                self.llm_provider.provider_name,
                self.llm_provider.model_name,
                type(exc).__name__,
                (perf_counter() - started_at) * 1000,
            )
            raise

        total_usage = generation.usage

        try:
            draft = self._parse_draft(
                generation
            )

        except PageCompositionSemanticValidationError as exc:
            logger.warning(
                "page_composition_semantic_validation_failed "
                "provider=%s model=%s error_type=%s",
                self.llm_provider.provider_name,
                self.llm_provider.model_name,
                type(exc).__name__,
            )

            repaired_generation = await self._repair_draft(
                request=request,
                invalid_generation=generation,
                validation_error=str(exc),
                response_schema=response_schema,
            )

            total_usage = self._combine_usage(
                generation.usage,
                repaired_generation.usage,
            )

            generation = repaired_generation

            try:
                draft = self._parse_draft(
                    generation
                )
            except (
                ValueError,
                ValidationError,
                TypeError,
            ) as repair_exc:
                self._raise_invalid_response(
                    exc=repair_exc,
                )

        except (
            ValueError,
            ValidationError,
            TypeError,
        ) as exc:
            self._raise_invalid_response(
                exc=exc,
            )

        logger.info(
            "page_composition_succeeded "
            "provider=%s model=%s latency_ms=%.2f",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
            (perf_counter() - started_at) * 1000,
        )

        return PageCompositionResponse(
            result=complete_databases(
                drop_unrequested_databases(
                    lock_composition_content(normalize_task_blocks(draft, request.instruction), request.instruction),
                    request.instruction,
                ),
                request.instruction,
            ),
            provider=self.llm_provider.provider_name,
            model=self.llm_provider.model_name,
            usage=(
                PageCompositionUsage(
                    prompt_tokens=total_usage.prompt_tokens,
                    completion_tokens=total_usage.completion_tokens,
                    total_tokens=total_usage.total_tokens,
                )
                if total_usage is not None
                else None
            ),
        )

    def _parse_draft(
        self,
        generation: LLMGenerationResult,
    ) -> PageCompositionDraft:
        raw_draft = parse_json_object(
            generation.text
        )

        draft = PageCompositionDraft.model_validate(
            raw_draft
        )

        validate_page_composition_semantics(
            draft
        )

        return draft

    async def _repair_draft(
        self,
        request: PageCompositionRequest,
        invalid_generation: LLMGenerationResult,
        validation_error: str,
        response_schema: dict,
    ) -> LLMGenerationResult:
        system_prompt, user_prompt = (
            build_page_composition_repair_prompt(
                instruction=request.instruction,
                invalid_draft=invalid_generation.text,
                validation_error=validation_error,
                context=request.context,
            )
        )

        logger.info(
            "page_composition_repair_started "
            "provider=%s model=%s",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
        )

        try:
            generation = await self.llm_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=MAX_NEW_TOKENS,
                response_schema=response_schema,
            )
        except Exception as exc:
            logger.warning(
                "page_composition_repair_failed "
                "provider=%s model=%s error_type=%s",
                self.llm_provider.provider_name,
                self.llm_provider.model_name,
                type(exc).__name__,
            )
            raise

        return generation

    def _combine_usage(
        self,
        first: LLMTokenUsage | None,
        second: LLMTokenUsage | None,
    ) -> LLMTokenUsage | None:
        if first is None or second is None:
            return None

        return LLMTokenUsage(
            prompt_tokens=(
                first.prompt_tokens
                + second.prompt_tokens
            ),
            completion_tokens=(
                first.completion_tokens
                + second.completion_tokens
            ),
            total_tokens=(
                first.total_tokens
                + second.total_tokens
            ),
        )

    def _raise_invalid_response(
        self,
        exc: Exception,
    ) -> None:
        logger.warning(
            "page_composition_invalid_response "
            "provider=%s model=%s "
            "error_type=%s",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
            type(exc).__name__,
        )

        raise InvalidLLMResponseError(
            "Page composition response is invalid."
        ) from exc
