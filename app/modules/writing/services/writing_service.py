import logging
from time import perf_counter

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMProvider
from app.modules.writing.prompts import build_writing_prompt
from app.modules.writing.schemas import WritingRequest, WritingResponse


logger = logging.getLogger(__name__)


class WritingService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    async def process(self, request: WritingRequest) -> WritingResponse:
        system_prompt, user_prompt = build_writing_prompt(
            action=request.action,
            text=request.text,
            language=request.language,
        )
        started_at = perf_counter()
        logger.info(
            "writing_started operation=%s provider=%s model=%s",
            request.action.value,
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
        )
        try:
            result = await self.llm_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=1000,
            )
        except Exception as exc:
            logger.warning(
                "writing_failed operation=%s provider=%s model=%s "
                "error_type=%s latency_ms=%.2f",
                request.action.value,
                self.llm_provider.provider_name,
                self.llm_provider.model_name,
                type(exc).__name__,
                (perf_counter() - started_at) * 1000,
            )
            raise

        if not result.strip():
            raise InvalidLLMResponseError("Writing result is empty.")

        logger.info(
            "writing_succeeded operation=%s provider=%s model=%s latency_ms=%.2f",
            request.action.value,
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
            (perf_counter() - started_at) * 1000,
        )
        return WritingResponse(
            result=result.strip(),
            provider=self.llm_provider.provider_name,
            model=self.llm_provider.model_name,
        )
