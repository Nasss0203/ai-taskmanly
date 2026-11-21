import logging
import re
from time import perf_counter

from app.core.exceptions import InvalidLLMResponseError, WritingNotDoneError
from app.llm.base import LLMProvider, answered_by
from app.modules.writing.prompts import build_writing_prompt
from app.modules.writing.schemas import WritingAction, WritingRequest, WritingResponse
from app.modules.writing.schemas.writing_schema import WritingUsage
from app.modules.writing.services.writing_check import PROBLEMS, demanded_words, directives, writing_problem


logger = logging.getLogger(__name__)

DIRECTIVE_FREE = (WritingAction.SUMMARIZE, WritingAction.SHORTEN, WritingAction.CONTINUE, WritingAction.EXPAND)
DAY_HINT = re.compile(r"\s*[(（](?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[)）]")


class WritingService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        continue_llm_provider: LLMProvider | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.continue_llm_provider = continue_llm_provider

    async def _generate_checked(
        self, provider: LLMProvider, request: WritingRequest, system_prompt: str, user_prompt: str,
        demanded: set[str] = frozenset(),
    ):
        """Kế hoạch sửa tính năng viết (V4, DV3): a result failing the rule checks is
        generated once more with the reason; a second failure is reported."""
        note = ""
        for attempt in range(2):
            generation = await provider.generate(
                system_prompt=system_prompt + note, user_prompt=user_prompt, max_new_tokens=1000,
            )
            result = generation.text
            if request.action is WritingAction.TRANSLATE:
                # The prompt names days in English in the source ("thứ Năm (Thursday)");
                # the hint is no part of the translation.
                result = DAY_HINT.sub("", result)
            copied = request.action is WritingAction.CONTINUE and result.strip().startswith(request.text.strip())
            if request.action is WritingAction.CONTINUE and result.startswith(request.text):
                result = result[len(request.text):]
            if not result.strip() and not copied:
                raise InvalidLLMResponseError("Writing result is empty.")
            problem = ("copied" if not result.strip() else
                       writing_problem(request.action, request.text, result.strip(), request.language, demanded))
            if problem is None:
                return generation, result
            logger.warning("writing_check_failed operation=%s problem=%s attempt=%d",
                           request.action.value, problem, attempt + 1)
            note = f"\n\nLẦN TRƯỚC KẾT QUẢ CHƯA ĐẠT: {PROBLEMS[problem]}. Hãy làm lại đúng yêu cầu ở trên."
        raise WritingNotDoneError(problem)

    async def process(self, request: WritingRequest) -> WritingResponse:
        provider = (
            self.continue_llm_provider
            if request.action is WritingAction.CONTINUE
            and self.continue_llm_provider is not None
            else self.llm_provider
        )
        cleaned, dropped = directives(request.text)
        demanded = demanded_words(dropped)
        if dropped and request.action in DIRECTIVE_FREE:
            logger.warning("writing_directive_removed operation=%s count=%d", request.action.value, len(dropped))
            if not cleaned:
                raise WritingNotDoneError("followed_instruction")
            request = request.model_copy(update={"text": cleaned})
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
            generation, result = await self._generate_checked(provider, request, system_prompt, user_prompt, demanded)
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


        logger.info(
            "writing_succeeded operation=%s provider=%s model=%s latency_ms=%.2f",
            request.action.value,
            provider.provider_name,
            provider.model_name,
            (perf_counter() - started_at) * 1000,
        )
        provider_name, model_name = answered_by(generation, provider)
        return WritingResponse(
            result=result if request.action is WritingAction.CONTINUE else result.strip(),
            provider=provider_name,
            model=model_name,
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
