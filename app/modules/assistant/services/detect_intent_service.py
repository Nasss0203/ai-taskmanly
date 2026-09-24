from app.infrastructure.llm.base import LLMProvider
from app.infrastructure.llm.registry import get_llm_provider
from app.modules.assistant.intent import AssistantIntent
from app.modules.assistant.schemas.context_schema import CurrentContext
from app.modules.assistant.prompts.detect_intent_prompt import (
    DETECT_INTENT_SYSTEM_PROMPT,
)


class DetectIntentService:
    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
    ):
        self.llm_provider = llm_provider

    def detect(
        self,
        message: str,
        current_context: CurrentContext | None = None,
    ) -> AssistantIntent:
        user_prompt = self._build_user_prompt(
            message=message,
            current_context=current_context,
        )

        result = self._get_llm_provider().generate(
            system_prompt=DETECT_INTENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_new_tokens=20,
        )

        result = result.strip().upper()

        if "CREATE_TASK" in result:
            return AssistantIntent.CREATE_TASK

        if "ANALYZE_SPRINT" in result:
            return AssistantIntent.ANALYZE_SPRINT

        if "NEEDS_CLARIFICATION" in result:
            return AssistantIntent.NEEDS_CLARIFICATION

        return AssistantIntent.GENERAL_CHAT
    
    def _build_user_prompt(
        self,
        message: str,
        current_context: CurrentContext | None,
    ) -> str:
        if current_context is None:
            context_text = "NONE"
        else:
            context_text = (
                f"{current_context.type.value} "
                f"(id={current_context.id})"
            )

        return f"""
    Current context:
    {context_text}

    User message:
    {message}
    """.strip()

    def _get_llm_provider(self) -> LLMProvider:
        if self.llm_provider is not None:
            return self.llm_provider

        return get_llm_provider()


detect_intent_service = DetectIntentService()