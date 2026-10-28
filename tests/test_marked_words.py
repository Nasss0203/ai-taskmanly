import asyncio

import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_service import IntentService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


# Folding drops marks: "Đích", "Táo" and "Dịch vụ" after "và" are names, not
# the commands "dịch" and "tạo".
@pytest.mark.parametrize("source", [
    "tích Mua sữa và Đích đến quý 4 trong trang sub man",
    "xoá Mua sữa và Táo đỏ trong trang sub man",
    "tích Mua sữa và Dịch vụ khách hàng trong trang sub man",
    "xoá Mua sữa và Dịch vụ khách hàng trong trang sub man",
    "xoá Mua sữa và Đội A báo cáo trong trang sub man",
])
def test_names_that_fold_to_a_command_are_one_edit(source) -> None:
    provider = FakeLLMProvider([])
    result = asyncio.run(IntentService(provider).process(IntentRequest(instruction=source)))
    assert result.result.intent == "MODIFY_PAGE"
    assert provider.calls == []


@pytest.mark.parametrize("source", [
    "tích Mua sữa và dịch tài liệu sang tiếng Anh trong trang sub man",
    "tích Mua sữa và tạo trang mới",
    "tich Mua sua va tao trang moi",
])
def test_real_second_commands_stay_unclear(source) -> None:
    provider = FakeLLMProvider([])
    result = asyncio.run(IntentService(provider).process(IntentRequest(instruction=source)))
    assert result.result.intent == "UNCLEAR"
