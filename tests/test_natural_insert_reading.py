"""Kế hoạch dùng Gemini (A4b): FastAPI reads the "thêm" sentences NestJS admits (A4) the same way."""

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import AiPageContext
from app.modules.modification_planner.services.explicit_content import mentions_position, parse_explicit_blocks
from app.modules.modification_planner.services.explicit_plan import plan_explicit_content
from app.modules.modification_planner.services.sentence_normalize import normalize_edit_instruction
from app.modules.page_intent.services.page_reference_evidence import detect_with_titles
from scripts.evaluate_generation import CONTEXTS

MEETING = ("Hội họp tuần",)


def edit_of(sentence: str, titles=MEETING) -> str | None:
    return detect_with_titles(normalize_edit_instruction(sentence), titles=titles).instruction


@pytest.mark.parametrize(("sentence", "instruction"), [
    ("nhờ bạn thêm việc gọi thợ sửa ống nước ở trang Hội họp tuần luôn giúp mình", "thêm việc gọi thợ sửa ống nước"),
    ("bạn thêm to-do mua bút bi vào trang Hội họp tuần hộ mình được không", "thêm to-do mua bút bi"),
    ("thêm hai to-do in tài liệu, đặt phòng vào trang Hội họp tuần với", "thêm hai to-do in tài liệu, đặt phòng"),
])
def test_polite_words_after_a_real_page_are_dropped(sentence, instruction) -> None:
    assert edit_of(sentence) == instruction


def test_words_after_the_page_that_are_content_stay() -> None:
    assert "với bạn" in edit_of("thêm to-do đi chơi với bạn ở trang Hội họp tuần")


def test_a_title_ending_in_a_polite_word_is_still_the_title() -> None:
    assert edit_of("thêm việc gọi khách vào trang Ăn trưa luôn", ("Ăn trưa luôn",)) == "thêm việc gọi khách"


def test_without_a_page_the_sentence_is_read_as_before() -> None:
    assert parse_explicit_blocks("thêm việc gọi thợ luôn") == [("TODO", "Gọi thợ luôn")]


@pytest.mark.parametrize(("sentence", "normalized"), [
    ("bạn ghi việc nộp báo cáo quý", "ghi việc nộp báo cáo quý"),
    ("cho mình ghi các việc mua bút, mua vở", "ghi các việc mua bút, mua vở"),
    ("mình cần ghi việc nộp báo cáo quý", "ghi việc nộp báo cáo quý"),
])
def test_polite_words_before_ghi_are_dropped(sentence, normalized) -> None:
    assert normalize_edit_instruction(sentence) == normalized


def test_a_note_and_an_overwrite_read_as_before() -> None:
    assert normalize_edit_instruction("ghi chú nhớ mang laptop") == 'thêm ghi chú "nhớ mang laptop"'
    assert parse_explicit_blocks("ghi đè trang Hội họp tuần") is None


@pytest.mark.parametrize(("instruction", "blocks"), [
    ("ghi việc nộp báo cáo quý", [("TODO", "Nộp báo cáo quý")]),
    ("ghi các việc mua bút, mua vở", [("TODO", "Mua bút"), ("TODO", "Mua vở")]),
    ("thêm hai to-do in tài liệu, đặt phòng", [("TODO", "In tài liệu"), ("TODO", "Đặt phòng")]),
    ("thêm ba việc gọi khách, gửi báo giá, chốt lịch", [("TODO", "Gọi khách"), ("TODO", "Gửi báo giá"), ("TODO", "Chốt lịch")]),
    ("thêm to-do mua hai hộp sữa", [("TODO", "Mua hai hộp sữa")]),
    ("thêm câu họp dời sang thứ Năm xuống dưới cùng", [("TEXT", "Họp dời sang thứ Năm")]),
    ("thêm đề mục Tổng kết", [("HEADER", "Tổng kết")]),
])
def test_explicit_blocks_of_natural_insertions(instruction, blocks) -> None:
    assert parse_explicit_blocks(instruction) == blocks


@pytest.mark.parametrize("instruction", [
    "thêm câu họp dời sang thứ Năm xuống dưới cùng",
    "thêm việc gọi khách ở dưới cùng",
    "thêm việc gọi khách vào cuối cùng trang",
])
def test_the_bottom_of_the_page_is_a_place(instruction) -> None:
    assert mentions_position(instruction)


def meeting() -> AiPageContext:
    return AiPageContext.model_validate(CONTEXTS["meeting"])


def test_a_sentence_at_the_bottom_goes_after_the_last_block() -> None:
    plan = plan_explicit_content("thêm câu họp dời sang thứ Năm xuống dưới cùng", meeting(), None)
    operation = plan.operations[0]
    assert (operation.parentBlockId, operation.afterBlockId) == (None, "b5")
    assert [(block.type, block.content.text) for block in operation.blocks] == [("TEXT", "Họp dời sang thứ Năm")]


def test_ghi_into_a_real_section() -> None:
    plan = plan_explicit_content("ghi việc chuẩn bị slide vào phần Tuần họp", meeting(), None)
    assert [(block.type, block.content.text) for block in plan.operations[0].blocks] == [("TODO", "Chuẩn bị slide")]

@pytest.mark.parametrize(("instruction", "blocks"), [
    ("chèn một đoạn ghi chú mỗi người tự mang theo pin dự phòng", [("TEXT", "Mỗi người tự mang theo pin dự phòng")]),
    ("thêm một dòng ghi chú nhớ mang laptop", [("TEXT", "Nhớ mang laptop")]),
    ("ghi một đoạn ghi chú họp dời sang thứ năm", [("TEXT", "Họp dời sang thứ năm")]),
    ("thêm đoạn chữ phòng họp đổi sang tầng ba", [("TEXT", "Phòng họp đổi sang tầng ba")]),
    ('thêm đoạn ghi chú "nhớ mang laptop"', [("TEXT", "nhớ mang laptop")]),
    ("thêm các việc sau viết biên bản họp, sao lưu dữ liệu", [("TODO", "Viết biên bản họp"), ("TODO", "Sao lưu dữ liệu")]),
    ("ghi những việc sau đây in tài liệu, đặt phòng và gửi lịch",
     [("TODO", "In tài liệu"), ("TODO", "Đặt phòng"), ("TODO", "Gửi lịch")]),
    ("thêm ghi chú nhớ mang laptop", [("TEXT", "Nhớ mang laptop")]),
    ("thêm việc tuần sau họp", [("TODO", "Tuần sau họp")]),
    ("thêm việc sau giờ học", [("TODO", "Sau giờ học")]),
    ("thêm tiêu đề Xuống phố", [("HEADER", "Xuống phố")]),
])
def test_content_without_kind_or_list_words(instruction, blocks) -> None:
    assert parse_explicit_blocks(instruction) == blocks


def test_one_task_after_cac_viec_sau_is_unsure() -> None:
    assert parse_explicit_blocks("thêm các việc sau viết biên bản họp") is None


def test_a_heading_moved_down_to_the_page_end() -> None:
    edit = edit_of("ghi tiêu đề Dự trù tiền bạc xuống cuối trang Hội họp tuần")
    plan = plan_explicit_content(edit, meeting(), None)
    operation = plan.operations[0]
    assert (operation.parentBlockId, operation.afterBlockId) == (None, "b5")
    assert [(block.type, block.content.text) for block in operation.blocks] == [("HEADER", "Dự trù tiền bạc")]


@pytest.mark.parametrize(("sentence", "blocks"), [
    ("ghi checklist in tài liệu, đặt phòng vào trang Hội họp tuần giúp mình", [("TODO", "In tài liệu"), ("TODO", "Đặt phòng")]),
    ("thêm checklist in tài liệu, đặt phòng ở cuối trang Hội họp tuần", [("TODO", "In tài liệu"), ("TODO", "Đặt phòng")]),
    ("thêm danh sách gồm in tài liệu, đặt phòng xuống dưới cùng trang Hội họp tuần nhé",
     [("TODO", "In tài liệu"), ("TODO", "Đặt phòng")]),
    ("thêm ba việc in tài liệu, đặt phòng, gửi lịch vào trang Hội họp tuần luôn giúp mình",
     [("TODO", "In tài liệu"), ("TODO", "Đặt phòng"), ("TODO", "Gửi lịch")]),
    ("nhờ bạn ghi các việc in tài liệu, đặt phòng và gửi lịch vào trang Hội họp tuần luôn",
     [("TODO", "In tài liệu"), ("TODO", "Đặt phòng"), ("TODO", "Gửi lịch")]),
    ("ở trang Hội họp tuần thêm các việc sau in tài liệu, đặt phòng với", [("TODO", "In tài liệu"), ("TODO", "Đặt phòng")]),
    ("ghi đề mục Tổng kết tuần vào trang Hội họp tuần", [("HEADER", "Tổng kết tuần")]),
    ("thêm đề mục Tổng kết tuần ở cuối trang Hội họp tuần luôn", [("HEADER", "Tổng kết tuần")]),
    ("nhờ bạn thêm tiêu đề Tổng kết tuần xuống dưới cùng trang Hội họp tuần với", [("HEADER", "Tổng kết tuần")]),
    ("nhờ bạn chèn tiêu đề Dự trù tiền bạc xuống cuối trang Hội họp tuần", [("HEADER", "Dự trù tiền bạc")]),
    ("ghi câu họp dời sang thứ năm vào trang Hội họp tuần", [("TEXT", "Họp dời sang thứ năm")]),
    ("thêm một câu nhớ mang laptop ở cuối trang Hội họp tuần luôn", [("TEXT", "Nhớ mang laptop")]),
    ("nhờ bạn ghi câu ai đi muộn thì nhắn nhóm xuống dưới cùng trang Hội họp tuần với", [("TEXT", "Ai đi muộn thì nhắn nhóm")]),
    ("ghi một đoạn ghi chú họp dời sang thứ năm xuống cuối trang Hội họp tuần", [("TEXT", "Họp dời sang thứ năm")]),
    ("ghi danh sách in tài liệu, đặt phòng và gửi lịch vào trang Hội họp tuần", None),
    ("bạn ghi hộ mình checklist in tài liệu, đặt phòng vào trang Hội họp tuần được không", None),
])
def test_loose_sentences_read_by_rule_or_left_unsure(sentence, blocks) -> None:
    assert parse_explicit_blocks(edit_of(sentence)) == blocks
