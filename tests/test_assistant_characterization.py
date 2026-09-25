import json
import sys

from app.modules.assistant.intent import AssistantIntent
from app.modules.assistant.schemas.assistant_schema import AssistantResponse
from app.modules.assistant.services.assistant_service import AssistantService
from app.modules.assistant.services.detect_intent_service import DetectIntentService
from app.modules.task.schemas.task_schema import TaskGenerationResponse
from app.modules.task.services.generate_task_service import GenerateTaskService
from tests.fakes.fake_llm_provider import FakeLLMProvider


def build_assistant(
    responses: list[str],
) -> tuple[AssistantService, FakeLLMProvider]:
    provider = FakeLLMProvider(responses)
    service = AssistantService(
        intent_detector=DetectIntentService(llm_provider=provider),
        task_generator=GenerateTaskService(llm_provider=provider),
        llm_provider=provider,
    )
    return service, provider


def test_general_chat_path() -> None:
    service, provider = build_assistant(
        [
            "GENERAL_CHAT",
            "JWT là một tiêu chuẩn dùng để truyền thông tin đã ký.",
        ]
    )

    response = service.process(message="JWT là gì?")

    assert isinstance(response, AssistantResponse)
    assert response.intent is AssistantIntent.GENERAL_CHAT
    assert response.data == {
        "message": "JWT là một tiêu chuẩn dùng để truyền thông tin đã ký."
    }
    assert len(provider.calls) == 2
    assert provider.calls[0]["max_new_tokens"] == 20
    assert "app.infrastructure.llm.qwen" not in sys.modules


def test_create_task_path_returns_validated_task() -> None:
    generated_task = {
        "title": "Thêm đăng nhập Google",
        "description": "Cho phép người dùng đăng nhập bằng Google OAuth.",
        "priority": "HIGH",
        "estimate": 3,
        "acceptance_criteria": [
            "Người dùng có thể bắt đầu OAuth flow.",
            "Hệ thống tạo phiên đăng nhập sau callback hợp lệ.",
        ],
    }
    service, provider = build_assistant(
        [
            "CREATE_TASK",
            json.dumps(generated_task, ensure_ascii=False),
        ]
    )

    response = service.process(
        message="Tạo task thêm chức năng đăng nhập bằng Google."
    )

    assert isinstance(response, AssistantResponse)
    assert response.intent is AssistantIntent.CREATE_TASK
    assert response.data == generated_task
    assert TaskGenerationResponse(**response.data).model_dump() == generated_task
    assert len(provider.calls) == 2
    assert provider.calls[1]["max_new_tokens"] == 400
    assert "app.infrastructure.llm.qwen" not in sys.modules
