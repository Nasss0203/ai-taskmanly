"""D-72: pages created from natural Vietnamese sentences, drafted by rule."""

import pytest

from app.modules.modification_planner.services.explicit_content import parse_explicit_blocks
from app.modules.modification_planner.services.sentence_normalize import normalize_create_instruction
from app.modules.page_composition.services.content_lock import compose_explicit_page
from app.modules.page_composition.services.database_blocks import compose_table_page


def page_of(sentence: str):
    draft = compose_explicit_page(normalize_create_instruction(sentence))
    if draft is None:
        return None
    return draft.page.title, [(block.type, block.content.text) for block in draft.blocks]


def table_of(sentence: str):
    draft = compose_table_page(normalize_create_instruction(sentence))
    if draft is None:
        return None
    database = draft.databases[0]
    return draft.page.title, database.name, [(prop.name, prop.type, [option.name for option in prop.options or []])
                                             for prop in database.properties]


@pytest.mark.parametrize(("sentence", "title", "blocks"), [
    ("bạn ơi tạo trang Quản lý khách hàng có danh sách việc cần làm liên hệ nhà cung cấp, đặt vé máy bay và sao lưu dữ liệu",
     "Quản lý khách hàng",
     [("TODO", "Liên hệ nhà cung cấp"), ("TODO", "Đặt vé máy bay"), ("TODO", "Sao lưu dữ liệu")]),
    ("tạo cho mình trang Nhật ký đọc sách với các việc chuẩn bị tài liệu họp, đi siêu thị, đặt bàn ăn tối",
     "Nhật ký đọc sách",
     [("TODO", "Chuẩn bị tài liệu họp"), ("TODO", "Đi siêu thị"), ("TODO", "Đặt bàn ăn tối")]),
    ("giúp mình tạo trang Tiệc cuối năm, trong đó có các mục Việc tuần sau, Ngân sách, Vấn đề", "Tiệc cuối năm",
     [("HEADER", "Việc tuần sau"), ("HEADER", "Ngân sách"), ("HEADER", "Vấn đề")]),
    ("tạo trang Chi tiêu tháng 11, trong đó có các mục Vấn đề, Mục tiêu, Tiến độ nha", "Chi tiêu tháng 11",
     [("HEADER", "Vấn đề"), ("HEADER", "Mục tiêu"), ("HEADER", "Tiến độ")]),
    ("cho mình làm trang Chi tiêu tháng 11 với ba mục Ghi chú, Việc tuần sau, Rủi ro nha", "Chi tiêu tháng 11",
     [("HEADER", "Ghi chú"), ("HEADER", "Việc tuần sau"), ("HEADER", "Rủi ro")]),
    ("làm trang Họp nhóm thứ hai với ba mục Tiến độ, Ngân sách, Mục tiêu giúp mình", "Họp nhóm thứ hai",
     [("HEADER", "Tiến độ"), ("HEADER", "Ngân sách"), ("HEADER", "Mục tiêu")]),
    ("trang mới tên Dự án website mới, chia ba phần Mục tiêu, Ngân sách và Việc tuần sau nhé", "Dự án website mới",
     [("HEADER", "Mục tiêu"), ("HEADER", "Ngân sách"), ("HEADER", "Việc tuần sau")]),
    ("tạo trang Sách và phim với hai mục Đã xem, Muốn xem", "Sách và phim",
     [("HEADER", "Đã xem"), ("HEADER", "Muốn xem")]),
    ("nhờ bạn lập trang Họp lớp cuối năm chia làm ba phần Khách mời, Thực đơn, Chi phí nhé", "Họp lớp cuối năm",
     [("HEADER", "Khách mời"), ("HEADER", "Thực đơn"), ("HEADER", "Chi phí")]),
])
def test_natural_pages_drafted_by_rule(sentence, title, blocks) -> None:
    assert page_of(sentence) == (title, blocks)


@pytest.mark.parametrize("sentence", [
    "cho mình làm trang Chi tiêu tháng 11 với hai mục Ghi chú, Việc tuần sau, Rủi ro",
    "tạo trang Kế hoạch với ba mục Mục tiêu, Ngân sách",
])
def test_a_count_that_does_not_match_is_left_to_the_model(sentence) -> None:
    assert page_of(sentence) is None


def test_trong_do_inside_a_title_stays() -> None:
    found = page_of("tạo trang Kế hoạch trong đó ghi mục tiêu quý gồm Doanh thu, Chi phí")
    assert found is None or found[0].startswith("Kế hoạch trong đó")


@pytest.mark.parametrize(("sentence", "title", "table", "columns"), [
    ("nhờ bạn tạo trang Kế hoạch du lịch Đà Nẵng và trong đó có bảng Công việc các cột Tên việc, Người phụ trách, Hạn chót",
     "Kế hoạch du lịch Đà Nẵng", "Công việc",
     [("Tên việc", "TITLE", []), ("Người phụ trách", "TEXT", []), ("Hạn chót", "DATE", [])]),
    ("cho mình làm trang Quản lý khách hàng có bảng Công việc, các cột Tên việc, Người phụ trách, Trạng thái gồm "
     "Chưa đọc, Đang đọc và Đã đọc với", "Quản lý khách hàng", "Công việc",
     [("Tên việc", "TITLE", []), ("Người phụ trách", "TEXT", []),
      ("Trạng thái", "SELECT", ["Chưa đọc", "Đang đọc", "Đã đọc"])]),
    ("mình cần trang Dự án website mới có bảng Sách gồm cột Tên sách, Tác giả và cột Trạng thái có các lựa chọn "
     "Chưa làm, Đang làm và Xong nha", "Dự án website mới", "Sách",
     [("Tên sách", "TITLE", []), ("Tác giả", "TEXT", []), ("Trạng thái", "SELECT", ["Chưa làm", "Đang làm", "Xong"])]),
    ("nhờ bạn tạo trang Ăn sạch có bảng Thực đơn, các cột Món ăn, Nguyên liệu và Tình trạng có Chưa mua, Đang giao "
     "và Đủ hàng nhé", "Ăn sạch", "Thực đơn",
     [("Món ăn", "TITLE", []), ("Nguyên liệu", "TEXT", []), ("Tình trạng", "SELECT", ["Chưa mua", "Đang giao", "Đủ hàng"])]),
    ("phiền bạn lập trang Tập đàn có bảng Bài tập, cột Tên bài, Nhạc sĩ và cột Mức độ lựa chọn Mới tập, Tập quen "
     "và Thuần thục nha", "Tập đàn", "Bài tập",
     [("Tên bài", "TITLE", []), ("Nhạc sĩ", "TEXT", []), ("Mức độ", "SELECT", ["Mới tập", "Tập quen", "Thuần thục"])]),
    ("nhờ bạn tạo trang Nấu ăn có bảng Món, các cột Tên món, Giá và Kết quả có Ngon và Phải làm lại",
     "Nấu ăn", "Món",
     [("Tên món", "TITLE", []), ("Giá", "TEXT", []), ("Kết quả", "SELECT", ["Ngon", "Phải làm lại"])]),
    ("tạo trang Bếp có bảng Kho gồm cột Tên, Món có sẵn", "Bếp", "Kho",
     [("Tên", "TITLE", []), ("Món có sẵn", "TEXT", [])]),
])
def test_natural_tables_drafted_by_rule(sentence, title, table, columns) -> None:
    assert table_of(sentence) == (title, table, columns)


def test_a_page_edit_reads_a_to_do_list_too() -> None:
    assert parse_explicit_blocks("thêm danh sách việc cần làm gọi khách, gửi báo giá") == [
        ("TODO", "Gọi khách"), ("TODO", "Gửi báo giá")]
