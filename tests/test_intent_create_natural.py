import asyncio
import json

import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_rules import deterministic_result
from app.modules.intent.services.intent_service import IntentService
from app.modules.modification_planner.services.sentence_normalize import normalize_edit_instruction
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def model(intent) -> FakeLLMProvider:
    return FakeLLMProvider([json.dumps({"intent": intent, "writingAction": None, "language": None})] * 2)


def read(instruction, provider, titles=()):
    request = IntentRequest(instruction=instruction, pageTitles=list(titles))
    return asyncio.run(IntentService(provider).process(request)).result.intent


def rules(instruction, titles=()):
    found = deterministic_result(IntentRequest(instruction=normalize_edit_instruction(instruction),
                                               pageTitles=list(titles)))
    return None if found is None else found.intent


@pytest.mark.parametrize("instruction", [
    "dựng trang Quản lý chi tiêu tháng Mười",
    "lên một trang Lịch học kỳ này giúp mình",
    "tạo một bảng theo dõi chi tiêu với các cột Ngày, Khoản chi, Số tiền",
    "làm bảng Danh sách khách mời với các cột Tên, Số điện thoại, Đã xác nhận",
    "tạo checklist chuẩn bị đi biển gồm kem chống nắng, khăn tắm, nón",
    "tạo ghi chú Họp nhóm thứ Sáu",
    "tạo một tài liệu Quy trình onboarding",
    "tạo sổ tay Học tiếng Nhật",
    "khởi tạo trang Dự án website bán hàng",
])
def test_the_model_creating_a_new_page_or_list_is_trusted(instruction) -> None:
    assert read(instruction, model("CREATE_PAGE")) == "CREATE_PAGE"


@pytest.mark.parametrize("instruction", [
    "mua trà biếu ông bà nội, nạp tiền điện thoại cho mẹ, cắt tóc ở tiệm anh Ba, ba việc này cho vào trang mới tên Thực đơn nhà mình nhé",
    "bảng Nhật ký luyện nghe với các cột Bài nghe, Số phút luyện, Điểm tự chấm, đặt trong trang mới Chuyến đi Phú Quốc tháng Tư nhé",
    "ghi giúp mình các việc mua sữa, đóng tiền nhà, sửa xe vào một trang mới tên Việc tuần này",
    "đặt các mục Ý tưởng, Ngân sách, Lịch trình vào một trang mới tên Du lịch hè",
])
def test_content_put_into_a_new_page_creates_it(instruction) -> None:
    assert rules(instruction) in (None, "CREATE_PAGE")
    assert read(instruction, model("CREATE_PAGE")) == "CREATE_PAGE"
    assert read(instruction, model("MODIFY_PAGE")) != "MODIFY_PAGE"


@pytest.mark.parametrize("instruction", [
    "thêm việc gọi thợ vào trang mới tạo hôm qua",
    "thêm việc gọi thợ vào trang mới nhất",
    "chép đoạn này vào trang mới lập",
])
def test_a_recently_created_page_is_not_a_new_page(instruction) -> None:
    assert read(instruction, model("CREATE_PAGE")) != "CREATE_PAGE"


@pytest.mark.parametrize("instruction", [
    "tạo một trang tên Sổ thu chi gia đình rồi ghi các việc trả hai cuốn sách thư viện, thay vòi sen nhà tắm",
    "cho mình tạo một trang tên Nuôi mèo con lần đầu rồi ghi các việc học thuộc mười từ tiếng Đức, nộp hồ sơ học bổng",
    "tạo trang Đi chợ cuối tuần rồi thêm các việc mua thịt, mua rau, mua trái cây",
])
def test_creating_a_page_then_writing_its_tasks_is_one_command(instruction) -> None:
    assert rules(instruction) == "CREATE_PAGE"
    assert read(instruction, model("CREATE_PAGE")) == "CREATE_PAGE"


@pytest.mark.parametrize("instruction", [
    "tạo trang Kho mới rồi chia sẻ trang Kho cũ cho nhóm",
    "tạo trang Kho mới rồi thêm việc gọi thợ vào trang Kho cũ",
    "tạo trang Test rồi dịch đoạn này sang tiếng Anh",
])
def test_a_second_command_on_another_target_still_asks(instruction) -> None:
    assert read(instruction, model("CREATE_PAGE")) == "UNCLEAR"


@pytest.mark.parametrize("instruction", [
    "mở một trang mới tên Ghi chép đọc sách",
    "mở trang mới Đọc sách tháng này gồm các mục Sách đang đọc, Trích dẫn hay",
    "thêm một trang mới tên Công thức bánh",
    "có thể tạo giúp mình trang Sổ tay nấu ăn không",
])
def test_opening_or_adding_a_new_page_creates_it(instruction) -> None:
    assert rules(instruction) in (None, "CREATE_PAGE")
    assert read(instruction, model("CREATE_PAGE")) == "CREATE_PAGE"


@pytest.mark.parametrize(("instruction", "expected"), [
    ("mở trang Ôn thi cuối kỳ", "OTHER"),
    ("mở trang mới tạo hôm qua", "OTHER"),
])
def test_opening_an_existing_page_still_reads_it(instruction, expected) -> None:
    assert read(instruction, model("CREATE_PAGE")) == expected


def test_adding_a_named_page_without_new_is_unchanged() -> None:
    assert read("thêm trang Lịch trực nhật cho cả phòng", model("CREATE_PAGE")) != "CREATE_PAGE"


@pytest.mark.parametrize("instruction", [
    "trang mới Sắm đồ Tết Bính Ngọ gồm ba phần Ai cùng tham gia, Lý do bắt đầu và Hạng mục chính",
    "ba phần Các mốc cần nhớ, Ai cùng tham gia, Hạng mục chính, đặt vào một trang mới tên Luyện nghe tiếng Hàn nha",
    "trang mới Giảm năm ký trước hè gồm ba phần Đường link hay, Ai cùng tham gia và Các mốc cần nhớ",
])
def test_a_section_named_with_a_question_word_is_not_a_question(instruction) -> None:
    assert rules(instruction) != "PAGE_QUESTION"
    assert read(instruction, model("CREATE_PAGE")) == "CREATE_PAGE"


@pytest.mark.parametrize(("instruction", "titles"), [
    ("ai đang làm việc Gọi thợ trong trang Kho cũ?", ["Kho cũ"]),
    ("trang mới Kho cũ gồm những mục nào?", ["Kho cũ"]),
])
def test_a_real_question_about_a_page_is_still_a_question(instruction, titles) -> None:
    assert rules(instruction, titles) == "PAGE_QUESTION"


@pytest.mark.parametrize("instruction", [
    "tạo bảng Chi tiêu trong trang Kho cũ",
    "tạo ghi chú Họp nhóm ở trang Kho cũ",
    "công khai trang mới lên mạng",
])
def test_a_list_or_note_inside_an_existing_page_is_not_a_new_page(instruction) -> None:
    assert read(instruction, model("CREATE_PAGE")) != "CREATE_PAGE"


def test_a_conservative_model_answer_is_not_promoted() -> None:
    assert read("tạo một bảng theo dõi chi tiêu với các cột Ngày, Khoản chi", model("OTHER")) == "OTHER"
    assert read("dựng trang Quản lý chi tiêu tháng Mười", model("UNCLEAR")) == "UNCLEAR"


def test_a_new_page_named_like_a_real_page_still_asks() -> None:
    assert read("tạo một bảng Kho cũ với các cột Ngày, Khoản chi", model("CREATE_PAGE"), titles=["Kho cũ"]) == "UNCLEAR"
