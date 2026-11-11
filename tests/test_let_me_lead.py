import asyncio

import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_service import IntentService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def intent(instruction: str):
    provider = FakeLLMProvider([])
    response = asyncio.run(IntentService(provider).process(IntentRequest(instruction=instruction)))
    return response.model, response.result.intent


@pytest.mark.parametrize(("instruction", "expected"), [  # D-58
    ("cho mình tạo trang Kế hoạch học kỳ 2 gồm đặt vé, mua quà", "CREATE_PAGE"),
    ("cho tôi tạo trang Họp nhóm có bảng Việc với cột Tên việc, Hạn chót", "CREATE_PAGE"),
    ("cho mình một trang mới tên Nhật ký", "CREATE_PAGE"),
    ("cho mình ghi thêm việc gọi cho khách hàng vào trang Hội họp tuần", "MODIFY_PAGE"),
    ("cho mình thêm nộp báo cáo tuần vào phần Môn Toán trong trang Ôn thi cuối kỳ", "MODIFY_PAGE"),
])
def test_cho_minh_before_a_command_is_read_by_rule(instruction, expected) -> None:
    assert intent(instruction) == ("intent-rules-v1", expected)


def test_cho_minh_before_an_existing_page_is_no_new_page() -> None:  # D-58
    from app.modules.modification_planner.services.sentence_normalize import normalize_instruction

    sentence = "cho mình trang Ôn thi cuối kỳ thêm checklist cập nhật lịch họp, đặt vé máy bay"
    assert not normalize_instruction(sentence).startswith("tạo trang")


@pytest.mark.parametrize(("instruction", "expected"), [  # D-58
    ("cho mình xem trang Hội họp tuần", "OTHER"),
    ("cho mình thêm việc gọi khách vào trang Hội họp tuần", "MODIFY_PAGE"),
])
def test_other_cho_minh_sentences_stay(instruction, expected) -> None:
    assert intent(instruction) == ("intent-rules-v1", expected)
