import pytest

from app.modules.modification_planner.services.explicit_content import parse_explicit_blocks
from app.modules.modification_planner.services.sentence_text import command_text


# Kế hoạch câu tự nhiên (N1, N2): the Page and polite words before the verb.
@pytest.mark.parametrize(("instruction", "command"), [
    ("ở trang Hội họp tuần sửa Xem xét báo cáo tháng 9 thành Xem xét báo cáo tháng 10",
     "sửa Xem xét báo cáo tháng 9 thành Xem xét báo cáo tháng 10"),
    ("bạn ơi, ở trang Hội họp tuần sửa A thành B nhé", "sửa A thành B"),
    ("trang Hội họp tuần: đổi A thành B", "đổi A thành B"),
    ("on the Weekly sync page, change A to B", "change A to B"),
    ("giúp mình ở trang Hội họp tuần xoá dòng Gọi khách", "xoá dòng Gọi khách"),
    ("ở trang Hội họp tuần tích xong Gọi khách", "tích xong Gọi khách"),
    ("mình muốn sửa A thành B", "sửa A thành B"),
    ("thêm to-do Sửa trang chủ", "thêm to-do Sửa trang chủ"),  # "trang" inside content
])
def test_a_leading_page_only_names_the_target(instruction: str, command: str) -> None:
    assert command_text(instruction) == command


def test_a_leading_page_before_an_insertion() -> None:
    assert parse_explicit_blocks("trong trang Hội họp tuần thêm to-do Gọi khách") == [("TODO", "Gọi khách")]


# Kế hoạch nội dung không ngoặc kép (K1, K2, K4): no quotes needed.
@pytest.mark.parametrize(("instruction", "expected"), [
    ("thêm to-do sửa máy in", [("TODO", "Sửa máy in")]),
    ("thêm to-do xoá file log cũ", [("TODO", "Xoá file log cũ")]),
    ("thêm to-do thu hồi quyền admin", [("TODO", "Thu hồi quyền admin")]),
    ("thêm đoạn văn Ai chịu trách nhiệm?", [("TEXT", "Ai chịu trách nhiệm?")]),
    ("thêm ghi chú nhớ mang laptop", [("TEXT", "Nhớ mang laptop")]),
    ("thêm danh sách mua sắm gồm sữa, trứng, bánh mì", [("TODO", "Sữa"), ("TODO", "Trứng"), ("TODO", "Bánh mì")]),
])
def test_verbs_and_marks_in_the_content_are_data(instruction: str, expected: list) -> None:
    assert parse_explicit_blocks(instruction) == expected
