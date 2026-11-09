import asyncio

import pytest

from app.modules.page_composition.schemas.page_composition_schema import PageCompositionRequest
from app.modules.page_composition.services.database_blocks import compose_table_page
from app.modules.page_composition.services.page_composition_service import (
    EXPLICIT_PAGE_MODEL,
    PageCompositionService,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def columns(draft) -> list[tuple[str, str, list[str]]]:
    return [(p.name, p.type, [o.name for o in p.options or []]) for p in draft.databases[0].properties]


@pytest.mark.parametrize(("instruction", "title", "table", "expected"), [
    ("tạo trang Kế hoạch đọc sách có bảng theo dõi sách với cột tên sách, tác giả, trạng thái",
     "Kế hoạch đọc sách", "Theo dõi sách",
     [("Tên sách", "TITLE", []), ("Tác giả", "TEXT", []), ("Trạng thái", "TEXT", [])]),
    ("tạo trang Thử L6 có bảng Sách với cột Tên sách, Tình trạng gồm Đang đọc, Đã đọc", "Thử L6", "Sách",
     [("Tên sách", "TITLE", []), ("Tình trạng", "SELECT", ["Đang đọc", "Đã đọc"])]),
    ("tạo trang Chi tiêu có bảng Chi tiêu gồm cột Khoản chi, Số tiền, Ngày, Loại (Ăn uống, Đi lại)", "Chi tiêu",
     "Chi tiêu", [("Khoản chi", "TITLE", []), ("Số tiền", "NUMBER", []), ("Ngày", "DATE", []),
                  ("Loại", "SELECT", ["Ăn uống", "Đi lại"])]),
    ("Tôi cần một trang quản lý công việc của nhóm có bảng Tasks với cột Tên, Người phụ trách, Hạn chót",
     "Quản lý công việc của nhóm", "Tasks",
     [("Tên", "TITLE", []), ("Người phụ trách", "TEXT", []), ("Hạn chót", "DATE", [])]),
    ("tao trang Chi tieu co bang Chi tieu voi cot Khoan chi, So tien, Ngay", "Chi tieu", "Chi tieu",
     [("Khoan chi", "TITLE", []), ("So tien", "NUMBER", []), ("Ngay", "DATE", [])]),
])
def test_a_page_with_only_a_listed_table_is_drafted_by_rule(instruction, title, table, expected) -> None:
    provider = FakeLLMProvider([])
    response = asyncio.run(PageCompositionService(provider).process(PageCompositionRequest(instruction=instruction)))
    assert provider.calls == []
    assert response.model == EXPLICIT_PAGE_MODEL
    draft = response.result
    assert draft.page.title == title
    assert [b.type for b in draft.blocks] == ["HEADER", "DATABASE_VIEW"]
    assert draft.blocks[0].content.text == title
    assert draft.databases[0].name == table
    assert columns(draft) == expected
    assert draft.databases[0].rows == []


@pytest.mark.parametrize("instruction", [
    "Tạo trang Đọc sách có bảng Sách gồm cột Tên, Trạng thái (Đang đọc, Đã đọc) với 2 dòng mẫu",
    "Tạo trang Cho thuê nhà gồm các việc: lập bản đồ, xác định giá thuê và có bảng Tasks gồm cột Tên",
    "create an expense tracker page with columns Item, Amount, Date",
    "tạo trang Kế hoạch có bảng theo dõi",
])
def test_other_table_pages_are_left_to_the_model(instruction) -> None:
    assert compose_table_page(instruction) is None
