import asyncio
import json

import pytest

from app.modules.modification_planner.services.sentence_normalize import normalize_create_instruction
from app.modules.page_composition.schemas.page_composition_schema import PageCompositionDraft, PageCompositionRequest
from app.modules.page_composition.services import content_lock
from app.modules.page_composition.services.content_lock import compose_explicit_page
from app.modules.page_composition.services.database_blocks import compose_table_page
from app.modules.page_composition.services.page_composition_service import PageCompositionService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def page_of(sentence):
    draft = compose_explicit_page(normalize_create_instruction(sentence))
    if draft is None:
        return None
    return draft.page.title, [(block.type, block.content.text) for block in draft.blocks]


def columns_of(sentence):
    draft = compose_table_page(normalize_create_instruction(sentence))
    return None if draft is None else [prop.name for prop in draft.databases[0].properties]


def draft(title, blocks):
    return {
        "schemaVersion": 1, "type": "PAGE_COMPOSITION", "page": {"title": title},
        "blocks": [{"ref": f"b{index}", "type": kind, "content": {"text": text, **({"checked": False} if kind == "TODO" else {})}}
                   for index, (kind, text) in enumerate(blocks, 1)],
        "databases": [],
    }


def kept(sentence, title, blocks):
    result = content_lock.keep_user_words(PageCompositionDraft.model_validate(draft(title, blocks)), sentence)
    return result.page.title, [(block.type, block.content.text) for block in result.blocks]


@pytest.mark.parametrize(("sentence", "title", "items"), [
    ("Làm trang Chăm sóc cây cảnh. Có 3 phần là Tưới nước, Bón phân, Cắt tỉa.", "Chăm sóc cây cảnh",
     ["Tưới nước", "Bón phân", "Cắt tỉa"]),
    ("tạo trang Kế hoạch học tập gồm 3 phần là Toán, Lý, Hoá", "Kế hoạch học tập", ["Toán", "Lý", "Hoá"]),
    ("tạo trang Ôn tập Sinh học có phần Tế bào, phần Di truyền và phần Tiến hoá", "Ôn tập Sinh học",
     ["Tế bào", "Di truyền", "Tiến hoá"]),
    ("tạo trang Ăn kiêng, có mục Thực đơn, mục Calo và mục Cân nặng", "Ăn kiêng", ["Thực đơn", "Calo", "Cân nặng"]),
    ("tạo trang Học Guitar, nội dung có các phần Hợp âm cơ bản, Bài tập ngón, Bài hát muốn tập", "Học Guitar",
     ["Hợp âm cơ bản", "Bài tập ngón", "Bài hát muốn tập"]),
    ("tạo trang Kế hoạch marketing quý 1, chia làm 4 phần: Mục tiêu, Kênh, Ngân sách, Đo lường",
     "Kế hoạch marketing quý 1", ["Mục tiêu", "Kênh", "Ngân sách", "Đo lường"]),
    ("tạo trang Hà Nội, Huế gồm các mục Ăn uống, Chỗ ở", "Hà Nội, Huế", ["Ăn uống", "Chỗ ở"]),
    ("tạo trang Triết học gồm các mục Thế nào là đủ, Hạnh phúc là gì", "Triết học", ["Thế nào là đủ", "Hạnh phúc là gì"]),
    ("tạo trang Máy tính gồm hai mục Phần mềm, Phần cứng", "Máy tính", ["Phần mềm", "Phần cứng"]),
])
def test_sections_keep_only_the_words_the_user_listed(sentence, title, items) -> None:
    assert page_of(sentence) == (title, [("HEADER", item) for item in items])


@pytest.mark.parametrize(("sentence", "title", "items"), [
    ("tạo trang Sửa xe, các bước: thay nhớt, kiểm tra phanh, bơm bánh", "Sửa xe",
     ["Thay nhớt", "Kiểm tra phanh", "Bơm bánh"]),
    ("Tạo trang Mua sắm tuần này. Cần mua: trứng, sữa, bánh mì, rau cải", "Mua sắm tuần này",
     ["Trứng", "Sữa", "Bánh mì", "Rau cải"]),
])
def test_a_title_stops_before_the_words_leading_into_a_list(sentence, title, items) -> None:
    assert page_of(sentence) == (title, [("TODO", item) for item in items])


def test_a_column_list_after_la_keeps_the_first_column_name() -> None:
    assert columns_of("tạo trang Dự án website có bảng Công việc, các cột là Tên việc, Người làm, Hạn chót") == [
        "Tên việc", "Người làm", "Hạn chót"]


WEDDING = "Mình đang lên kế hoạch cho đám cưới, làm giúp trang Đám cưới tháng Chạp, chia ra mấy phần: Khách mời, Ngân sách, Lịch trình"


def test_a_numbered_section_heading_becomes_the_listed_name() -> None:
    _title, blocks = kept(WEDDING, "Đám cưới tháng Chạp", [
        ("HEADER", "Phần 1: Khách mời"), ("TODO", "Lập danh sách"), ("HEADER", "Phần 2: Ngân sách"),
        ("HEADER", "3. Lịch trình")])
    assert blocks == [("HEADER", "Khách mời"), ("TODO", "Lập danh sách"), ("HEADER", "Ngân sách"), ("HEADER", "Lịch trình")]


def test_a_listed_name_followed_by_a_colon_becomes_a_heading_and_text() -> None:
    sentence = "giúp tạo trang Họp lớp 10 năm, các mục cần có: Địa điểm, Danh sách liên lạc, Chi phí dự kiến"
    _, blocks = kept(sentence, "Họp lớp 10 năm", [
        ("TODO", "Địa điểm: Trường THPT Nguyễn Trãi"), ("TODO", "Danh sách liên lạc: Lan, Huy"),
        ("TODO", "Chi phí dự kiến: 5 triệu")])
    assert blocks == [("HEADER", "Địa điểm"), ("TEXT", "Trường THPT Nguyễn Trãi"), ("HEADER", "Danh sách liên lạc"),
                      ("TEXT", "Lan, Huy"), ("HEADER", "Chi phí dự kiến"), ("TEXT", "5 triệu")]


def test_listed_names_with_words_added_are_trimmed_back() -> None:
    _, blocks = kept("tạo trang Ra mắt sản phẩm gồm hai phần Chuẩn bị và Sau ra mắt", "Ra mắt sản phẩm", [
        ("HEADER", "Chuẩn bị cho sự kiện ra mắt"), ("TODO", "Đặt phòng"), ("HEADER", "Sau ra mắt sản phẩm")])
    assert blocks == [("HEADER", "Chuẩn bị"), ("TODO", "Đặt phòng"), ("HEADER", "Sau ra mắt")]


def test_listed_tasks_with_words_added_are_trimmed_and_the_lead_line_dropped() -> None:
    sentence = "tạo trang Bé đi học với các việc chuẩn bị: mua cặp, bọc sách, may đồng phục"
    _, blocks = kept(sentence, "Bé đi học", [
        ("TODO", "Các việc chuẩn bị cho bé đi học:"), ("TODO", "Mua cặp cho bé"), ("TODO", "Bọc sách cho bé"),
        ("TODO", "May đồng phục cho bé")])
    assert blocks == [("TODO", "Mua cặp"), ("TODO", "Bọc sách"), ("TODO", "May đồng phục")]


def test_names_are_not_trimmed_when_not_every_listed_name_is_found() -> None:
    sentence = "tạo trang Bé đi học với các việc chuẩn bị: mua cặp, bọc sách, may đồng phục"
    blocks = [("TODO", "Mua cặp cho bé"), ("TODO", "Bọc sách cẩn thận"), ("TODO", "Ủi đồ")]
    assert kept(sentence, "Bé đi học", blocks) == ("Bé đi học", blocks)


def test_a_draft_for_a_sentence_without_a_list_is_kept() -> None:
    blocks = [("HEADER", "Phần 1: Mục tiêu"), ("TODO", "Các bước:"), ("TODO", "Mở tài khoản: tháng 1")]
    assert kept("tạo trang Kế hoạch tiết kiệm", "Kế hoạch tiết kiệm", blocks) == ("Kế hoạch tiết kiệm", blocks)


def test_a_colon_line_is_kept_as_a_task_when_tasks_were_asked() -> None:
    sentence = "làm trang Chuyển nhà, trong đó ghi các việc đóng thùng sách, báo cắt internet, thuê xe tải"
    blocks = [("TODO", "Đóng thùng sách: tối thứ Bảy"), ("TODO", "Báo cắt internet"), ("TODO", "Thuê xe tải")]
    assert [kind for kind, _ in kept(sentence, "Chuyển nhà", blocks)[1]] == ["TODO", "TODO", "TODO"]


@pytest.mark.parametrize(("sentence", "model_title", "title"), [
    ("tạo trang Danh sách phim hay đi nha", "Danh sách phim hay đi", "Danh sách phim hay"),
    ("tạo trang Kế hoạch tiết kiệm nhé", "Kế hoạch tiết kiệm nhé", "Kế hoạch tiết kiệm"),
    ("tạo trang Bữa trưa mang đi nha", "Bữa trưa mang đi", "Bữa trưa mang đi"),
    ("tạo trang Đi chợ", "Đi chợ", "Đi chợ"),
    ("tạo trang Học bơi đi", "Học bơi", "Học bơi"),
    ("cho mình xin một trang mới tên Thực đơn nhà mình", "Thực đơn nhà mình", "Thực đơn nhà mình"),
    ("mua trà, cắt tóc, ba việc này cho vào trang mới tên Thực đơn nhà mình nhé", "Thực đơn nhà mình nhé",
     "Thực đơn nhà mình"),
    ("tạo trang Kế hoạch tiết kiệm giúp mình", "Kế hoạch tiết kiệm giúp mình", "Kế hoạch tiết kiệm"),
    ("tạo trang Ôn thi nha bạn", "Ôn thi nha bạn", "Ôn thi"),
    ("tạo trang Nhóm bạn thân", "Nhóm bạn thân", "Nhóm bạn thân"),
    ("tạo trang Lớp mình", "Lớp mình", "Lớp mình"),
    ("tạo trang Việc nhà mình đi nha", "Việc nhà mình đi nha", "Việc nhà mình"),
])
def test_filler_words_ending_the_sentence_leave_the_title(sentence, model_title, title) -> None:
    assert kept(sentence, model_title, [("TEXT", "Nội dung")])[0] == title


def test_the_service_keeps_the_user_words_in_a_model_draft() -> None:
    answer = json.dumps(draft("Đám cưới tháng Chạp", [
        ("HEADER", "Phần 1: Khách mời"), ("HEADER", "Phần 2: Ngân sách"), ("HEADER", "Phần 3: Lịch trình")]))
    response = asyncio.run(PageCompositionService(FakeLLMProvider([answer])).process(
        PageCompositionRequest(instruction=WEDDING)))
    assert [block.content.text for block in response.result.blocks] == ["Khách mời", "Ngân sách", "Lịch trình"]
