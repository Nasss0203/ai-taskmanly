from app.infrastructure.llm.base import LLMProvider
from app.infrastructure.llm.registry import get_llm_provider
from app.modules.assistant.intent import AssistantIntent
from app.modules.assistant.schemas.assistant_schema import AssistantResponse
from app.modules.assistant.schemas.context_schema import CurrentContext
from app.modules.assistant.services.detect_intent_service import (
    DetectIntentService,
    detect_intent_service,
)
from app.modules.task.services.generate_task_service import (
    GenerateTaskService,
    generate_task_service,
)


GENERAL_ASSISTANT_SYSTEM_PROMPT = (
    "Bạn là AI Assistant của Taskmanly. "
    "Trả lời ngắn gọn, rõ ràng và bằng tiếng Việt."
)


class AssistantService:
    def __init__(
        self,
        intent_detector: DetectIntentService = detect_intent_service,
        task_generator: GenerateTaskService = generate_task_service,
        llm_provider: LLMProvider | None = None,
    ):
        self.intent_detector = intent_detector
        self.task_generator = task_generator
        self.llm_provider = llm_provider


    def process(
        self,
        message: str,
        current_context: CurrentContext | None = None,
    ) -> AssistantResponse:
        intent = self.intent_detector.detect(
            message=message,
            current_context=current_context,
        )

        if intent == AssistantIntent.CREATE_TASK:
            result = self.task_generator.generate(message)

            return AssistantResponse(
                intent=intent,
                data=result,
            )

        if intent == AssistantIntent.ANALYZE_SPRINT:
            return AssistantResponse(
                intent=intent,
                data={
                    "message": (
                        "Đã nhận diện yêu cầu phân tích Sprint. "
                        "Bước tiếp theo cần truyền dữ liệu Sprint "
                        "từ NestJS vào AI."
                    )
                },
            )

        if intent == AssistantIntent.NEEDS_CLARIFICATION:
            return AssistantResponse(
                intent=intent,
                data={
                    "message": (
                        "Mình cần thêm thông tin để xử lý chính xác hơn. "
                        "Bạn có thể bổ sung mục tiêu, bối cảnh hoặc dữ liệu liên quan không?"
                    )
                },
            )

        response = self._get_llm_provider().generate(
            system_prompt=GENERAL_ASSISTANT_SYSTEM_PROMPT,
            user_prompt=message,
        )

        return AssistantResponse(
            intent=intent,
            data={
                "message": response,
            },
        )

    def _get_llm_provider(self) -> LLMProvider:
        if self.llm_provider is not None:
            return self.llm_provider

        return get_llm_provider()


assistant_service = AssistantService()
