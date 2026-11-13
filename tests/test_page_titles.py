import asyncio

import pytest
from pydantic import ValidationError

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_service import IntentService
from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_intent.services.page_reference_evidence import detect_page_reference, detect_with_titles


class NoModel:
    provider_name = "none"
    model_name = "none"

    async def generate(self, *args, **kwargs):
        raise AssertionError("the rules must answer")


def intent(sentence: str, titles: list[str]):
    return asyncio.run(IntentService(NoModel()).process(IntentRequest(instruction=sentence, pageTitles=titles))).result


def page_intent(sentence: str, titles: list[str]):
    return asyncio.run(PageIntentService(NoModel()).process(
        PageIntentRequest(instruction=sentence, pageTitles=titles))).result


@pytest.mark.parametrize("sentence, title, instruction", [
    ("trong trang sub man ghi thêm đoạn văn phòng họp tầng 5 đang sửa nên tạm họp online giúp mình", "sub man",
     "ghi thêm đoạn văn phòng họp tầng 5 đang sửa nên tạm họp online giúp mình"),
    ("ở trang Hội họp tuần đổi 3. Đánh giá hiệu suất đội ngũ thành 3. Đánh giá hiệu suất đội ngũ cho cả nhóm đi",
     "Hội họp tuần", "đổi 3. Đánh giá hiệu suất đội ngũ thành 3. Đánh giá hiệu suất đội ngũ cho cả nhóm đi"),
    ("bạn thêm vào trang Hội họp tuần việc đặt bàn ăn tối giúp mình", "Hội họp tuần",
     "bạn thêm việc đặt bàn ăn tối giúp mình"),
    ("xóa việc đặt phòng khỏi trang sub man", "sub man", "xóa việc đặt phòng"),
])
def test_a_real_title_after_the_page_word_ends_the_name(sentence: str, title: str, instruction: str) -> None:
    evidence = detect_with_titles(sentence, titles=("Hội họp", "Hội họp tuần", "sub man", "sub"))
    assert (evidence.reference_type, evidence.title, evidence.instruction) == ("TITLE", title, instruction)


def test_page_word_inside_the_content_is_not_a_second_page() -> None:
    evidence = detect_with_titles("bảng Tasks ở trang Release 2.0 thêm dòng Tối ưu tốc độ tải trang nha",
                                  titles=("Release 2.0",))
    assert (evidence.reference_type, evidence.title) == ("TITLE", "Release 2.0")


@pytest.mark.parametrize("sentence", [
    "thêm việc gọi khách vào trang Hội họp tuần",
    "trong trang sub man ghi thêm đoạn văn phòng họp tầng 5 đang sửa",
    "chép việc A từ trang sub man sang trang Hội họp tuần",
])
def test_without_titles_nothing_changes(sentence: str) -> None:
    assert detect_with_titles(sentence, titles=()) == detect_page_reference(sentence)


def test_two_real_titles_after_the_page_word_still_ask() -> None:
    evidence = detect_with_titles("chép việc A từ trang sub man sang trang Hội họp tuần",
                                  titles=("sub man", "Hội họp tuần"))
    assert evidence.reference_type == "UNRESOLVED"


def test_a_real_title_not_after_the_page_word_is_not_used() -> None:
    sentence = "ghi chú họp ở Hội họp tuần thêm việc gọi khách"
    assert detect_with_titles(sentence, titles=("Hội họp tuần",)) == detect_page_reference(sentence)


def test_page_intent_reads_the_real_title_without_the_model() -> None:
    result = page_intent("trong trang sub man ghi thêm đoạn văn phòng họp tầng 5 đang sửa nên tạm họp online",
                         ["sub man"])
    assert (result.intent, result.referenceType, result.pageReference) == ("MODIFY_PAGE", "TITLE", "sub man")
    assert result.instruction == "ghi thêm đoạn văn phòng họp tầng 5 đang sửa nên tạm họp online"


@pytest.mark.parametrize("sentence, instruction", [
    ("ở trang Hội họp tuần đổi 3. Đánh giá hiệu suất đội ngũ thành 3. Đánh giá hiệu suất đội ngũ cho cả nhóm đi",
     "đổi 3. Đánh giá hiệu suất đội ngũ thành 3. Đánh giá hiệu suất đội ngũ cho cả nhóm"),
    ("bạn ơi ở trang Hội họp tuần sửa 1. Xem xét báo cáo doanh thu tháng 9 thành 1. Xem xét báo cáo doanh thu cho cả nhóm",
     "sửa 1. Xem xét báo cáo doanh thu tháng 9 thành 1. Xem xét báo cáo doanh thu cho cả nhóm"),
])
def test_rules_confirmed_by_a_real_title_need_no_model(sentence: str, instruction: str) -> None:
    result = page_intent(sentence, ["Hội họp tuần"])
    assert (result.referenceType, result.pageReference, result.instruction) == ("TITLE", "Hội họp tuần", instruction)


@pytest.mark.parametrize("sentence, title", [
    ("trang Hội họp tuần họp lúc mấy giờ", "Hội họp tuần"),
    ("cuộc họp ở trang Hội họp tuần diễn ra thứ mấy", "Hội họp tuần"),
    ("bạn ơi trang Hội họp tuần họp lúc mấy giờ", "Hội họp tuần"),
    ("bạn ơi trang sub man nói sau khi chuyển xong mất bao lâu", "sub man"),
])
def test_questions_keep_the_real_title(sentence: str, title: str) -> None:
    result = intent(sentence, [title])
    assert (result.intent, result.pageReference) == ("PAGE_QUESTION", title)


def test_questions_without_titles_read_as_before() -> None:
    try:
        found = intent("trang Hội họp tuần họp lúc mấy giờ", []).intent
    except AssertionError:
        found = "model"
    assert found != "PAGE_QUESTION"


def test_titles_are_limited() -> None:
    with pytest.raises(ValidationError):
        IntentRequest(instruction="xin chào", pageTitles=[f"Trang {index}" for index in range(6)])
    with pytest.raises(ValidationError):
        PageIntentRequest(instruction="xin chào", pageTitles=["x" * 256])
    assert IntentRequest(instruction="xin chào").pageTitles == []
