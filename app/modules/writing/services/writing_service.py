import logging
from time import perf_counter

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMProvider
from app.modules.writing.prompts import build_writing_prompt
from app.modules.writing.schemas import WritingAction, WritingRequest, WritingResponse
from app.modules.writing.schemas.writing_schema import WritingUsage


logger = logging.getLogger(__name__)


class WritingService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        continue_llm_provider: LLMProvider | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.continue_llm_provider = continue_llm_provider

    async def process(self, request: WritingRequest) -> WritingResponse:
        provider = (
            self.continue_llm_provider
            if request.action is WritingAction.CONTINUE
            and self.continue_llm_provider is not None
            else self.llm_provider
        )
        system_prompt, user_prompt = build_writing_prompt(
            action=request.action,
            text=request.text,
            language=request.language,
        )
        started_at = perf_counter()
        logger.info(
            "writing_started operation=%s provider=%s model=%s",
            request.action.value,
            provider.provider_name,
            provider.model_name,
        )
        try:
            generation = await provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=1000,
            )
        except Exception as exc:
            logger.warning(
                "writing_failed operation=%s provider=%s model=%s "
                "error_type=%s latency_ms=%.2f",
                request.action.value,
                provider.provider_name,
                provider.model_name,
                type(exc).__name__,
                (perf_counter() - started_at) * 1000,
            )
            raise

        result = generation.text
        if request.action is WritingAction.CONTINUE and result.startswith(request.text):
            result = result[len(request.text):]

        if not result.strip():
            raise InvalidLLMResponseError("Writing result is empty.")

        logger.info(
            "writing_succeeded operation=%s provider=%s model=%s latency_ms=%.2f",
            request.action.value,
            provider.provider_name,
            provider.model_name,
            (perf_counter() - started_at) * 1000,
        )
        return WritingResponse(
            result=result if request.action is WritingAction.CONTINUE else result.strip(),
            provider=provider.provider_name,
            model=provider.model_name,
            usage=(
                WritingUsage(
                    prompt_tokens=generation.usage.prompt_tokens,
                    completion_tokens=generation.usage.completion_tokens,
                    total_tokens=generation.usage.total_tokens,
                )
                if generation.usage is not None
                else None
            ),
        )
