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


def todos(*items: str) -> list[tuple[str, str]]:
    return [("TODO", item) for item in items]


@pytest.mark.parametrize(("sentence", "title", "blocks"), [
    ("mình muốn có trang Chuyển nhà với ba việc thuê xe tải, đóng thùng sách, báo cắt điện nha", "Chuyển nhà",
     todos("Thuê xe tải", "Đóng thùng sách", "Báo cắt điện")),
    ("mình muốn có trang Đi Đà Lạt với các việc đặt homestay, thuê xe máy, mua áo ấm", "Đi Đà Lạt",
     todos("Đặt homestay", "Thuê xe máy", "Mua áo ấm")),
    ("tôi muốn có trang Thi cuối kỳ gồm ôn chương 3, làm đề cũ, hỏi thầy phần khó", "Thi cuối kỳ",
     todos("Ôn chương 3", "Làm đề cũ", "Hỏi thầy phần khó")),
    ("mình cần trang Sửa nhà với các việc gọi thợ điện, mua sơn, dọn phòng khách", "Sửa nhà",
     todos("Gọi thợ điện", "Mua sơn", "Dọn phòng khách")),
    ("em muốn một trang Họp phụ huynh với hai việc in phiếu điểm, gửi thư mời", "Họp phụ huynh",
     todos("In phiếu điểm", "Gửi thư mời")),
    ("tạo trang mới Học bơi với danh sách mua kính bơi, đăng ký lớp buổi sáng và hỏi giá vé hồ bơi giúp mình",
     "Học bơi", todos("Mua kính bơi", "Đăng ký lớp buổi sáng", "Hỏi giá vé hồ bơi")),
    ("tạo trang Dọn nhà với danh sách lau cửa kính, giặt rèm, vứt đồ cũ", "Dọn nhà",
     todos("Lau cửa kính", "Giặt rèm", "Vứt đồ cũ")),
    ("tạo trang Mua sắm với checklist mua giày, mua tất, mua balo", "Mua sắm",
     todos("Mua giày", "Mua tất", "Mua balo")),
    ("tạo trang Học lái xe với danh sách việc đăng ký học, học lý thuyết, thi thử", "Học lái xe",
     todos("Đăng ký học", "Học lý thuyết", "Thi thử")),
    ("tạo trang Gia đình với việc cần làm đón con, nấu cơm và giặt đồ", "Gia đình",
     todos("Đón con", "Nấu cơm", "Giặt đồ")),
    ("tạo trang Dự án A, việc phải làm là viết đặc tả, vẽ giao diện và viết test", "Dự án A",
     todos("Viết đặc tả", "Vẽ giao diện", "Viết test")),
    ("tạo trang Chuẩn bị Tết, cần làm mấy việc dọn nhà, mua hoa, gói bánh chưng", "Chuẩn bị Tết",
     todos("Dọn nhà", "Mua hoa", "Gói bánh chưng")),
    ("tạo trang Văn phòng, các việc gồm in tài liệu, mua mực in, sửa máy lạnh", "Văn phòng",
     todos("In tài liệu", "Mua mực in", "Sửa máy lạnh")),
    ("tạo trang Việc nhà, cần làm: rửa bát, lau nhà, đổ rác", "Việc nhà", todos("Rửa bát", "Lau nhà", "Đổ rác")),
    ("tạo trang Ngày mai với to-do: dậy sớm, chạy bộ, ăn sáng", "Ngày mai", todos("Dậy sớm", "Chạy bộ", "Ăn sáng")),
    ("tạo trang Mua đồ với danh sách: sữa, trứng, bánh mì", "Mua đồ", todos("Sữa", "Trứng", "Bánh mì")),
    ("tạo trang Đọc sách với danh sách việc cần làm: mua sách, đọc 20 trang mỗi ngày, ghi chú", "Đọc sách",
     todos("Mua sách", "Đọc 20 trang mỗi ngày", "Ghi chú")),
    ("tạo trang Đi chợ có những việc như mua rau, mua thịt, mua trái cây", "Đi chợ",
     todos("Mua rau", "Mua thịt", "Mua trái cây")),
    ("tạo trang Đám cưới Lan với những việc cần làm là đặt nhà hàng, in thiệp, chọn váy", "Đám cưới Lan",
     todos("Đặt nhà hàng", "In thiệp", "Chọn váy")),
    ("tạo trang Cuối tuần gồm việc đi bơi, việc đọc sách, việc gọi điện cho bố", "Cuối tuần",
     todos("Đi bơi", "Đọc sách", "Gọi điện cho bố")),
    ("việc cần làm gồm mua quà sinh nhật, đặt bánh kem và gọi cho bà, lập trang Sinh nhật mẹ để ghi",
     "Sinh nhật mẹ", todos("Mua quà sinh nhật", "Đặt bánh kem", "Gọi cho bà")),
    ("việc cần làm: thay dầu xe, bơm lốp, rửa xe, tạo trang Bảo dưỡng xe cho mình", "Bảo dưỡng xe",
     todos("Thay dầu xe", "Bơm lốp", "Rửa xe")),
    ("ba việc sửa vòi nước, thay bóng đèn, dọn gác, lập trang Việc cuối tuần để ghi nha", "Việc cuối tuần",
     todos("Sửa vòi nước", "Thay bóng đèn", "Dọn gác")),
    ("tạo trang Kế hoạch tuần để ghi các việc nộp báo cáo, họp nhóm, tập gym", "Kế hoạch tuần",
     todos("Nộp báo cáo", "Họp nhóm", "Tập gym")),
    ("tạo một trang tên Sổ tay bếp rồi ghi các việc mua dao mới, thay khăn lau, dọn tủ lạnh", "Sổ tay bếp",
     todos("Mua dao mới", "Thay khăn lau", "Dọn tủ lạnh")),
    ("giúp mình tạo trang Du lịch Huế ghi các việc đặt vé tàu, đặt khách sạn, tìm quán ăn", "Du lịch Huế",
     todos("Đặt vé tàu", "Đặt khách sạn", "Tìm quán ăn")),
    ("tạo trang Học tiếng Anh rồi thêm các việc học 20 từ mới, nghe podcast, viết nhật ký", "Học tiếng Anh",
     todos("Học 20 từ mới", "Nghe podcast", "Viết nhật ký")),
    ("tạo trang Thể thao với các việc chạy 5 km và tập tạ", "Thể thao", todos("Chạy 5 km", "Tập tạ")),
    ("tạo trang Ăn kiêng với checklist bỏ đồ ngọt và uống trà xanh", "Ăn kiêng",
     todos("Bỏ đồ ngọt", "Uống trà xanh")),
])
def test_more_to_do_lists_drafted_by_rule(sentence, title, blocks) -> None:
    assert page_of(sentence) == (title, blocks)


@pytest.mark.parametrize("sentence", [
    "tạo trang Kế hoạch về cách tiết kiệm tiền, đầu tư và trả nợ",
    "tạo trang Lên kế hoạch team building cho công ty",
    "tạo trang Học nhạc với ba việc mua đàn, tìm thầy, tập gam và học bài đầu tiên",
    "tạo trang Nghỉ hè với danh sách những nơi muốn đi Đà Nẵng, Hội An, Huế",
    "tạo trang Ăn uống với danh sách các món phở, bún chả, bánh xèo",
    "tạo trang Sức khoẻ gồm uống đủ nước và ngủ trước 11 giờ",
    "hai việc sửa vòi nước, thay bóng đèn, dọn gác, lập trang Việc cuối tuần để ghi",
])
def test_lists_the_rules_are_unsure_of_stay_with_the_model(sentence) -> None:
    assert page_of(sentence) is None


def headers(*items: str) -> list[tuple[str, str]]:
    return [("HEADER", item) for item in items]


@pytest.mark.parametrize("first", [
    "Việc cần làm", "Danh sách việc", "Ghi chú", "Checklist", "Tiêu đề", "Trích dẫn", "Đoạn văn", "To-do",
    "Việc đã xong", "Ghi chú cuộc họp",
])
def test_a_first_section_named_like_a_block_kind_stays_a_section(first) -> None:
    assert page_of(f"tạo trang Họp tuần với các mục: {first}, Mục tiêu, Rủi ro") == (
        "Họp tuần", headers(first, "Mục tiêu", "Rủi ro"))


@pytest.mark.parametrize(("sentence", "blocks"), [
    ("tạo trang Họp tuần gồm: Ghi chú, Mục tiêu, Rủi ro", todos("Ghi chú", "Mục tiêu", "Rủi ro")),
    ("tạo trang Họp tuần gồm: Việc cần làm, Mục tiêu, Rủi ro", todos("Việc cần làm", "Mục tiêu", "Rủi ro")),
    ("tạo trang Họp tuần gồm Việc cần làm, Mục tiêu, Rủi ro", todos("Việc cần làm", "Mục tiêu", "Rủi ro")),
    ("tạo trang Họp tuần gồm Danh sách việc, Mục tiêu, Rủi ro", todos("Danh sách việc", "Mục tiêu", "Rủi ro")),
    ("tạo trang Họp tuần gồm: Checklist, Mục tiêu, Rủi ro", todos("Checklist", "Mục tiêu", "Rủi ro")),
    ("tạo trang Họp tuần gồm Đoạn văn, Mục tiêu, Rủi ro", todos("Đoạn văn", "Mục tiêu", "Rủi ro")),
    ("tạo trang Họp tuần với các mục: Mục tiêu, Ghi chú, Rủi ro", headers("Mục tiêu", "Ghi chú", "Rủi ro")),
    ("tạo trang Họp tuần gồm các phần: Việc cần làm, Mục tiêu và Rủi ro",
     headers("Việc cần làm", "Mục tiêu", "Rủi ro")),
])
def test_a_block_kind_word_alone_is_an_item(sentence, blocks) -> None:
    assert page_of(sentence) == ("Họp tuần", blocks)


@pytest.mark.parametrize("sentence", [
    "tạo trang Họp tuần gồm: Ghi chú cuộc họp, Mục tiêu, Rủi ro",
    "tạo trang Họp tuần gồm: Tiêu đề kế hoạch, Mục tiêu, Rủi ro",
    "tạo trang Họp tuần gồm Đoạn văn mở đầu, Mục tiêu, Rủi ro",
])
def test_one_block_or_many_items_is_left_to_the_model(sentence) -> None:
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
