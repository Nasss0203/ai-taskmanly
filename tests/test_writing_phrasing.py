import asyncio

import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_service import IntentService

SELECTED = "Cả nhóm họp xong sớm hôm nay."


class NoModel:
    provider_name = "none"
    model_name = "none"

    async def generate(self, *args, **kwargs):
        raise AssertionError("the rules must answer")


def intent(sentence: str, selected: str | None = SELECTED):
    request = IntentRequest(instruction=sentence, selectedText=selected)
    return asyncio.run(IntentService(NoModel()).process(request)).result


@pytest.mark.parametrize("sentence, action, language", [
    ("dịch qua tiếng Anh nhé", "TRANSLATE", "English"),
    ("dịch giúp mình phần này ra tiếng Anh", "TRANSLATE", "English"),
    ("mình cần bản tiếng Trung của đoạn này", "TRANSLATE", "Chinese"),
    ("mình cần bản dịch tiếng Anh của đoạn này", "TRANSLATE", "English"),
    ("đoạn này dịch sang tiếng Nhật giúp mình", "TRANSLATE", "Japanese"),
    ("chuyển đoạn này sang tiếng Hàn", "TRANSLATE", "Korean"),
    ("đổi đoạn này sang tiếng Anh giúp mình", "TRANSLATE", "English"),
    ("chuyển giúp mình đoạn này qua tiếng Anh", "TRANSLATE", "English"),
    ("phần này dịch ra tiếng Anh nhé", "TRANSLATE", "English"),
    ("viết lại đoạn này bằng tiếng Anh", "TRANSLATE", "English"),
    ("bạn sửa giúp mình đoạn này cho chuyên nghiệp được không", "IMPROVE", None),
    ("mình muốn đoạn này lịch sự hơn", "IMPROVE", None),
    ("sửa lại đoạn này cho dễ đọc hơn", "IMPROVE", None),
    ("sửa giúp mình mấy lỗi chính tả trong đoạn này", "IMPROVE", None),
    ("đoạn này đọc hơi cứng, viết lại giúp mình", "IMPROVE", None),
    ("làm đoạn này trôi chảy hơn", "IMPROVE", None),
    ("chỉnh lại câu chữ cho mượt hơn", "IMPROVE", None),
    ("viết lại cho trang trọng hơn", "IMPROVE", None),
    ("đọc rồi tóm tắt giúp mình đoạn này", "SUMMARIZE", None),
    ("đoạn này tóm tắt giúp mình", "SUMMARIZE", None),
    ("nêu ý chính của đoạn này", "SUMMARIZE", None),
    ("viết ngắn gọn lại", "SHORTEN", None),
    ("làm gọn đoạn này giúp mình", "SHORTEN", None),
    ("mình muốn đoạn này ngắn hơn", "SHORTEN", None),
    ("bạn rút ngắn đoạn này được không", "SHORTEN", None),
    ("cắt bớt cho ngắn hơn", "SHORTEN", None),
    ("làm cho đoạn này ngắn hơn", "SHORTEN", None),
    ("viết gọn lại đoạn này", "SHORTEN", None),
    ("viết lại ngắn gọn hơn", "SHORTEN", None),
    ("bổ sung thêm ý cho đoạn này", "EXPAND", None),
    ("viết chi tiết hơn", "EXPAND", None),
    ("viết rõ hơn đoạn này", "EXPAND", None),
    ("đoạn này viết dài thêm giúp mình", "EXPAND", None),
    ("thêm ví dụ cho đoạn này", "EXPAND", None),
    ("phát triển đoạn này thành đoạn dài hơn", "EXPAND", None),
    ("bạn viết thêm cho đoạn này dài hơn được không", "EXPAND", None),
    ("viết nối tiếp đoạn này", "CONTINUE", None),
    ("viết nốt đoạn này", "CONTINUE", None),
    ("Nội dung đang chọn cần mượt mà hơn", "IMPROVE", None),
])
def test_everyday_writing_commands_are_read_by_rules(sentence: str, action: str, language: str | None) -> None:
    result = intent(sentence)
    assert (result.intent, result.writingAction, result.language) == ("WRITING", action, language)


@pytest.mark.parametrize("sentence, action, language", [
    ("tóm tắt Dự án chậm một tuần vì thiếu người", "SUMMARIZE", None),
    ("sửa lỗi chính tả Khách hàng rất hài lòng với bản demo", "IMPROVE", None),
    ("viết ngắn lại nhóm mình cần thêm hai người để kịp tiến độ", "SHORTEN", None),
    ("viết dài hơn câu Khách hàng rất hài lòng với bản demo", "EXPAND", None),
    ("sản phẩm mới bán khá chạy trong tháng đầu tiên, dịch sang tiếng Anh giúp mình", "TRANSLATE", "English"),
])
def test_writing_with_the_text_in_the_sentence(sentence: str, action: str, language: str | None) -> None:
    result = intent(sentence, selected=None)
    assert (result.intent, result.writingAction, result.language) == ("WRITING", action, language)


@pytest.mark.parametrize("sentence", [
    "mình muốn trang Hội họp tuần ngắn hơn",
    "viết lại cho hay hơn",
    "đổi Gọi khách thành Gọi khách hàng",
])
def test_no_text_to_work_on_is_not_a_writing_draft(sentence: str) -> None:
    try:
        found = intent(sentence, selected=None).intent
    except AssertionError:
        found = "model"
    assert found != "WRITING"


REFERENCES = [
    ("dịch giúp mình nội dung này sang tiếng Anh", "TRANSLATE"),
    ("dịch văn bản này sang tiếng Nhật", "TRANSLATE"),
    ("dịch đoạn bên dưới sang tiếng Anh", "TRANSLATE"),
    ("dịch giùm tôi đoạn dưới đây sang tiếng Pháp", "TRANSLATE"),
    ("viết tiếp đoạn văn bên dưới cho mình", "CONTINUE"),
    ("mở rộng ý của đoạn trên", "EXPAND"),
    ("dịch đoạn trên sang tiếng Anh", "TRANSLATE"),
    ("tóm tắt nội dung bên dưới giúp mình", "SUMMARIZE"),
    ("viết lại đoạn văn phía trên cho mượt hơn", "IMPROVE"),
    ("rút gọn văn bản sau đây giúp mình", "SHORTEN"),
    ("mở rộng nội dung của đoạn đó", "EXPAND"),
    ("mình muốn nội dung này ngắn hơn", "SHORTEN"),
    ("làm văn bản này trôi chảy hơn", "IMPROVE"),
    ("nội dung này dịch sang tiếng Anh giúp mình", "TRANSLATE"),
    ("đoạn bên dưới tóm tắt giúp mình", "SUMMARIZE"),
    ("văn bản này gọn hơn được không", "SHORTEN"),
]


def _draft(sentence: str) -> bool:
    from app.modules.intent.services.writing_source import inline_writing_text

    try:
        found = intent(sentence, selected=None).intent
    except AssertionError:
        return False
    return found == "WRITING" and inline_writing_text(sentence) is not None


@pytest.mark.parametrize("sentence, action", REFERENCES)
def test_pointing_at_a_passage_reads_the_selection(sentence: str, action: str) -> None:
    result = intent(sentence)
    assert (result.intent, result.writingAction) == ("WRITING", action)


@pytest.mark.parametrize("sentence", [sentence for sentence, _ in REFERENCES])
def test_pointing_at_a_passage_without_one_asks(sentence: str) -> None:
    assert not _draft(sentence)


def test_every_dev_ask_form_asks() -> None:
    from evaluation.natural_vi_generator import DEV_BANK

    assert [sentence for sentence in DEV_BANK["writing"]["ask"] if _draft(sentence)] == []


def test_dev_ask_forms_point_at_passages_in_many_ways() -> None:
    from app.modules.intent.services.writing_source import PASSAGE_HEAD, PASSAGE_POINTER, _fold
    from evaluation.natural_vi_generator import DEV_BANK

    def pointed(sentence: str) -> bool:
        folded = " " + " ".join(_fold(word) for word in sentence.split()) + " "
        return any(f" {head} {pointer} " in folded for head in PASSAGE_HEAD for pointer in PASSAGE_POINTER
                   if f"{head} {pointer}" not in ("doan nay", "cai nay"))

    assert sum(pointed(sentence) for sentence in DEV_BANK["writing"]["ask"]) >= 10


@pytest.mark.parametrize("sentence", [
    "thêm việc viết báo cáo ngắn hơn vào trang Hội họp tuần",
    "thêm việc gọi khách vào trang trọng điểm",
    "sửa Gọi khách thành Gọi khách hàng ở trang Hội họp tuần",
])
def test_page_edits_stay_page_edits(sentence: str) -> None:
    assert intent(sentence, selected=None).intent == "MODIFY_PAGE"
