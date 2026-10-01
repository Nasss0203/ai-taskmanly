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
from app.modules.page_composition.validators import (
    PageCompositionSemanticValidationError,
    validate_page_composition_semantics,
)
from app.shared.json_parser import parse_json_object


logger = logging.getLogger(__name__)


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
                max_new_tokens=4000,
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
                "provider=%s model=%s error=%s",
                self.llm_provider.provider_name,
                self.llm_provider.model_name,
                str(exc),
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
                    generation=generation,
                    exc=repair_exc,
                )

        except (
            ValueError,
            ValidationError,
            TypeError,
        ) as exc:
            self._raise_invalid_response(
                generation=generation,
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
            result=draft,
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
                max_new_tokens=4000,
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
        generation: LLMGenerationResult,
        exc: Exception,
    ) -> None:
        logger.warning(
            "page_composition_invalid_response "
            "provider=%s model=%s "
            "error_type=%s error=%s raw_response=%r",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
            type(exc).__name__,
            str(exc),
            generation.text,
        )

        raise InvalidLLMResponseError(
            "Page composition response is invalid."
        ) from exc