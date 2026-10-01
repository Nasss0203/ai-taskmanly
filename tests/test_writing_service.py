import asyncio

import pytest

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMGenerationResult, LLMTokenUsage
from app.llm.providers.fake import FakeLLMProvider as ProductionFakeLLMProvider
from app.modules.writing.schemas import WritingAction, WritingRequest
from app.modules.writing.services import WritingService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


@pytest.mark.parametrize(
    ("action", "extra_fields"),
    [
        (WritingAction.IMPROVE, {}),
        (WritingAction.SHORTEN, {}),
        (WritingAction.EXPAND, {}),
        (WritingAction.SUMMARIZE, {}),
        (WritingAction.TRANSLATE, {"language": "English"}),
        (WritingAction.CONTINUE, {}),
    ],
    ids=["improve", "shorten", "expand", "summarize", "translate", "continue"],
)
def test_writing_action_uses_injected_provider(
    action: WritingAction,
    extra_fields: dict[str, str],
) -> None:
    provider = FakeLLMProvider([f"result for {action.value}"])
    service = WritingService(provider)
    request = WritingRequest(
        action=action,
        text="Nội dung cần xử lý.",
        **extra_fields,
    )

    response = asyncio.run(service.process(request))

    assert response.result == f"result for {action.value}"
    assert response.provider == "fake"
    assert response.model == "fake-model"
    assert response.usage is None
    assert len(provider.calls) == 1
    if action is WritingAction.TRANSLATE:
        assert provider.calls[0]["user_prompt"] == request.text
        assert extra_fields["language"] in provider.calls[0]["system_prompt"]
        assert "Hãy dịch toàn bộ văn bản người dùng" in provider.calls[0]["system_prompt"]
    elif action is WritingAction.SHORTEN:
        assert provider.calls[0]["user_prompt"] == request.text
        assert "Hãy rút gọn đáng kể văn bản người dùng" in provider.calls[0]["system_prompt"]
        assert "Kết quả phải ngắn hơn văn bản nguồn" in provider.calls[0]["system_prompt"]
    elif action is WritingAction.EXPAND:
        assert provider.calls[0]["user_prompt"] == request.text
        assert (
            "Mọi khẳng định trong kết quả phải có ý tương ứng trực tiếp trong văn bản nguồn"
            in provider.calls[0]["system_prompt"]
        )
        assert (
            "Chỉ được mở rộng cách diễn đạt của những ý đã tồn tại"
            in provider.calls[0]["system_prompt"]
        )
        assert (
            "Không được thêm hành động, tính năng, khả năng, lợi ích, nguyên nhân, kết quả, ví dụ, số liệu, cơ chế hoặc chi tiết mới"
            in provider.calls[0]["system_prompt"]
        )
        assert (
            "Nếu không thể viết dài hơn mà không thêm thông tin mới, hãy giữ nguyên văn bản nguồn hoặc chỉ paraphrase rất nhẹ"
            in provider.calls[0]["system_prompt"]
        )
        assert (
            "Không bắt buộc kết quả phải dài hơn văn bản nguồn"
            in provider.calls[0]["system_prompt"]
        )
        assert (
            "Việc giữ đúng nghĩa quan trọng hơn việc làm văn bản dài hơn"
            in provider.calls[0]["system_prompt"]
        )
    elif action is WritingAction.CONTINUE:
        assert provider.calls[0]["user_prompt"] == request.text
        assert (
            "Chỉ tạo phần văn bản mới cần nối ngay sau văn bản nguồn"
            in provider.calls[0]["system_prompt"]
        )
        assert "Chỉ trả về phần viết tiếp mới" in provider.calls[0]["system_prompt"]
        assert (
            "không lặp lại hoặc viết lại văn bản nguồn"
            in provider.calls[0]["system_prompt"]
        )
        assert (
            "Khi nguồn thiếu ngữ cảnh, viết tiếp ngắn và trung tính"
            in provider.calls[0]["system_prompt"]
        )
    else:
        assert f"Thao tác: {action.value}" in provider.calls[0]["user_prompt"]
    assert provider.calls[0]["max_new_tokens"] == 1000


def test_continue_strips_exact_source_prefix() -> None:
    provider = FakeLLMProvider(["Người dùng có thể quản lý công việc hiệu quả."])
    service = WritingService(provider)
    request = WritingRequest(action=WritingAction.CONTINUE, text="Người dùng có thể")

    response = asyncio.run(service.process(request))

    assert response.result == " quản lý công việc hiệu quả."


def test_continue_preserves_suffix_only() -> None:
    provider = FakeLLMProvider([" quản lý công việc hiệu quả."])
    service = WritingService(provider)
    request = WritingRequest(action=WritingAction.CONTINUE, text="Người dùng có thể")

    response = asyncio.run(service.process(request))

    assert response.result == " quản lý công việc hiệu quả."


def test_continue_rejects_source_only() -> None:
    source = "Taskmanly giúp nhóm quản lý công việc."
    provider = FakeLLMProvider([source])
    service = WritingService(provider)
    request = WritingRequest(action=WritingAction.CONTINUE, text=source)

    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(service.process(request))


def test_continue_rejects_whitespace_only_suffix() -> None:
    provider = FakeLLMProvider(["Người dùng có thể   "])
    service = WritingService(provider)
    request = WritingRequest(action=WritingAction.CONTINUE, text="Người dùng có thể")

    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(service.process(request))


def test_improve_trims_result() -> None:
    provider = FakeLLMProvider(["   Nội dung đã cải thiện.   "])
    service = WritingService(provider)
    request = WritingRequest(action=WritingAction.IMPROVE, text="Nội dung cần xử lý.")

    response = asyncio.run(service.process(request))

    assert response.result == "Nội dung đã cải thiện."


@pytest.mark.parametrize("action", list(WritingAction))
def test_writing_routes_to_selected_provider(action: WritingAction) -> None:
    default_provider = FakeLLMProvider([
        LLMGenerationResult(" default text ", LLMTokenUsage(10, 5, 15))
    ])
    default_provider.model_name = "qwen3:1.7b"
    continue_provider = FakeLLMProvider([
        LLMGenerationResult(" continuation text", LLMTokenUsage(20, 8, 28))
    ])
    continue_provider.model_name = "qwen3:4b-instruct"
    continue_provider.provider_name = "continue-fake"
    service = WritingService(default_provider, continue_provider)
    request = WritingRequest(action=action, text="Source", language="English")

    response = asyncio.run(service.process(request))

    selected = continue_provider if action is WritingAction.CONTINUE else default_provider
    unused = default_provider if action is WritingAction.CONTINUE else continue_provider
    assert len(selected.calls) == 1
    assert unused.calls == []
    assert selected.calls[0]["max_new_tokens"] == 1000
    assert response.provider == selected.provider_name
    assert response.model == selected.model_name
    assert response.usage is not None
    assert response.usage.model_dump() == (
        {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}
        if action is WritingAction.CONTINUE
        else {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    )
    assert response.result == (
        " continuation text" if action is WritingAction.CONTINUE else "default text"
    )


def test_continue_without_override_uses_default_provider() -> None:
    provider = FakeLLMProvider([" continuation text"])
    provider.model_name = "qwen3:1.7b"
    request = WritingRequest(action=WritingAction.CONTINUE, text="Source")

    response = asyncio.run(WritingService(provider).process(request))

    assert len(provider.calls) == 1
    assert response.model == "qwen3:1.7b"
    assert response.result == " continuation text"


def test_continue_prefix_stripping_preserves_usage() -> None:
    provider = FakeLLMProvider([
        LLMGenerationResult(
            "Người dùng có thể quản lý công việc.", LLMTokenUsage(20, 8, 28)
        )
    ])
    request = WritingRequest(action=WritingAction.CONTINUE, text="Người dùng có thể")

    response = asyncio.run(WritingService(provider).process(request))

    assert response.result == " quản lý công việc."
    assert response.usage is not None
    assert response.usage.model_dump() == {
        "prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28
    }


def test_production_fake_has_no_usage() -> None:
    generation = asyncio.run(ProductionFakeLLMProvider().generate("system", "user"))
    assert generation.text == "Fake AI response"
    assert generation.usage is None


def test_translate_requires_target_language() -> None:
    with pytest.raises(ValueError, match="language"):
        WritingRequest(
            action=WritingAction.TRANSLATE,
            text="Xin chào",
        )


def test_empty_text_is_rejected() -> None:
    with pytest.raises(ValueError):
        WritingRequest(action=WritingAction.IMPROVE, text="")


def test_target_language_alias_remains_supported() -> None:
    request = WritingRequest(
        action=WritingAction.TRANSLATE,
        text="Xin chào",
        targetLanguage="English",
    )

    assert request.language == "English"
