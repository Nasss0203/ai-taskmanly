import asyncio

import pytest

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
    assert len(provider.calls) == 1
    assert f"Thao tác: {action.value}" in provider.calls[0]["user_prompt"]
    assert provider.calls[0]["max_new_tokens"] == 1000


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
