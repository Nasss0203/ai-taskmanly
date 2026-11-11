import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_rules import deterministic_result
from app.modules.page_composition.services.database_blocks import compose_table_page


def intent(instruction: str):
    result = deterministic_result(IntentRequest(instruction=instruction))
    return result and (result.intent, result.needsClarification)


@pytest.mark.parametrize(("instruction", "options"), [  # D-42
    ("tạo trang Quản lý sách có bảng Sách với cột Tên sách, Tác giả và Trạng thái gồm Chưa đọc, Đang đọc và Đã đọc",
     ["Chưa đọc", "Đang đọc", "Đã đọc"]),
    ("tạo trang Tuyển dụng có bảng Ứng viên với cột Họ tên, Vị trí và Trạng thái gồm Đạt và Không đạt",
     ["Đạt", "Không đạt"]),
])
def test_a_status_column_after_and_is_no_second_page(instruction, options) -> None:
    assert intent(instruction) == ("CREATE_PAGE", False)
    draft = compose_table_page(instruction)
    status = [prop for db in draft.databases for prop in db.properties if prop.name == "Trạng thái"]
    assert status and status[0].type == "SELECT" and [option.name for option in status[0].options] == options


@pytest.mark.parametrize(("instruction", "expected"), [  # D-42
    ("tao trang Tuyen dung co bang Ung vien voi cot Ho ten, Vi tri va trang thai gom dat va khong dat", ("CREATE_PAGE", False)),
    ("tạo trang Sách có bảng Sách với cột Tên sách và Tình trạng gồm Đang đọc và Đã đọc", ("CREATE_PAGE", False)),
    ("thêm checklist vào trang A và trang B", ("UNCLEAR", True)),
    ("sửa trạng thái của Gọi khách ở trang Hội họp tuần", ("MODIFY_PAGE", False)),
])
def test_other_sentences_read_as_expected(instruction, expected) -> None:
    assert intent(instruction) == expected
