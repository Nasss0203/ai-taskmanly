import pytest

from app.modules.page_composition.schemas.page_composition_schema import PageCompositionDraft
from app.modules.page_composition.services.database_blocks import complete_databases


def draft() -> PageCompositionDraft:
    # Live: no DATABASE_VIEW, columns renamed, lines standing for the columns.
    return PageCompositionDraft.model_validate({
        "schemaVersion": 1, "type": "PAGE_COMPOSITION", "page": {"title": "Thử bảng AI"},
        "blocks": [
            {"ref": "h", "type": "HEADER", "content": {"text": "Trang Thử bảng AI"}, "styleConfig": {"level": 1}},
            {"ref": "t", "type": "TEXT", "content": {"text": "Danh sách nhiệm vụ."}},
            {"ref": "a", "type": "TEXT", "content": {"text": "Tên"}},
            {"ref": "b", "type": "TEXT", "content": {"text": "Trạng thái"}},
            {"ref": "c", "type": "TEXT", "content": {"text": "Todo"}},
        ],
        "databases": [{"ref": "db", "name": "Tasks", "properties": [
            {"ref": "p1", "name": "Name", "type": "TITLE"},
            {"ref": "p2", "name": "Status", "type": "SELECT",
             "options": [{"ref": "o1", "name": "To do"}, {"ref": "o2", "name": "Finished"}]},
        ], "views": [{"ref": "v", "name": "Bảng", "type": "TABLE"}], "rows": []}],
    })


def test_a_table_is_shown_with_the_users_column_names() -> None:
    result = complete_databases(draft(), "Tạo trang Thử bảng AI có bảng Tasks gồm cột Tên, Trạng thái (Todo, Done)")
    props = result.databases[0].properties
    assert [p.name for p in props] == ["Tên", "Trạng thái"]
    assert [o.name for o in props[1].options] == ["Todo", "Done"]
    assert [b.type for b in result.blocks] == ["HEADER", "TEXT", "DATABASE_VIEW"]
    assert result.blocks[2].databaseRef == "db" and result.blocks[2].viewRef == "v"


def test_columns_are_kept_when_the_count_differs() -> None:
    result = complete_databases(draft(), "Tạo trang có bảng Tasks gồm cột Tên, Trạng thái, Hạn chót")
    assert [p.name for p in result.databases[0].properties] == ["Name", "Status"]


def invented(rows: bool = True) -> PageCompositionDraft:
    return PageCompositionDraft.model_validate({
        "schemaVersion": 1, "type": "PAGE_COMPOSITION", "page": {"title": "Cho thuê nhà"},
        "blocks": [
            {"ref": "h", "type": "HEADER", "content": {"text": "Trang Cho thuê nhà"}, "styleConfig": {"level": 1}},
            {"ref": "t", "type": "TEXT", "content": {"text": "Dưới đây là danh sách các nhiệm vụ."}},
            {"ref": "s1", "type": "TEXT", "content": {"text": "Bảng Tasks gồm cột Tên và Trạng thái (Todo, Done)"}},
            {"ref": "s2", "type": "TEXT", "content": {"text": "Tạo bảng Tasks với các cột: Tên, Trạng thái"}},
            {"ref": "s3", "type": "TEXT", "content": {"text": "Trạng thái có thể là: Todo hoặc Done"}},
            {"ref": "n", "type": "TEXT", "content": {"text": "Ghi chú: nhớ gọi khách trước thứ Sáu."}},
            {"ref": "d1", "type": "TODO", "content": {"text": "Lập bản đồ khu vực", "checked": False}},
            {"ref": "d2", "type": "TODO", "content": {"text": "Xác định giá thuê", "checked": False}},
        ],
        "databases": [{"ref": "db", "name": "Tasks", "properties": [
            {"ref": "p1", "name": "Tên", "type": "TITLE"},
            {"ref": "p2", "name": "Trạng thái", "type": "SELECT",
             "options": [{"ref": "o1", "name": "Todo"}, {"ref": "o2", "name": "Done"}]},
        ], "views": [{"ref": "v", "name": "Bảng", "type": "TABLE"}],
            "rows": [{"ref": "r1", "values": {"p1": "Task 1", "p2": {"optionRef": "o1"}}},
                     {"ref": "r2", "values": {"p1": "Task 2", "p2": {"optionRef": "o1"}}}] if rows else []}],
    })


ONLY_TABLE = "Tạo trang Cho thuê nhà có bảng Tasks gồm cột Tên, Trạng thái (Todo, Done)"


def test_a_table_the_sentence_gives_no_rows_for_stays_empty() -> None:
    result = complete_databases(invented(), ONLY_TABLE)
    assert result.databases[0].rows == []


def test_a_table_only_request_drops_invented_todos_and_lines_about_the_columns() -> None:
    result = complete_databases(invented(), ONLY_TABLE)
    texts = [b.content.text for b in result.blocks if b.type != "DATABASE_VIEW"]
    assert texts == ["Trang Cho thuê nhà", "Dưới đây là danh sách các nhiệm vụ.", "Ghi chú: nhớ gọi khách trước thứ Sáu."]
    assert [b.type for b in result.blocks].count("DATABASE_VIEW") == 1


@pytest.mark.parametrize("sentence", [
    "Tạo trang Cho thuê nhà có bảng Tasks gồm cột Tên, Trạng thái (Todo, Done) gồm các dòng: Task 1, Task 2",
    "Tạo trang Cho thuê nhà có bảng Tasks gồm cột Tên, Trạng thái với 2 dòng mẫu",
    "Create a page Rent with a Tasks table with columns Name, Status and sample rows",
])
def test_rows_stay_when_the_sentence_asks_for_them(sentence) -> None:
    assert len(complete_databases(invented(), sentence).databases[0].rows) == 2


def test_listed_tasks_stay_next_to_a_table() -> None:
    sentence = "Tạo trang Cho thuê nhà gồm các việc: lập bản đồ khu vực, xác định giá thuê và có bảng Tasks gồm cột Tên"
    result = complete_databases(invented(), sentence)
    assert [b.content.text for b in result.blocks if b.type == "TODO"] == ["Lập bản đồ khu vực", "Xác định giá thuê"]


def test_a_page_without_a_table_is_untouched() -> None:
    page = invented(rows=False).model_dump(mode="json", exclude_none=True)
    page["databases"] = []
    draft_without = PageCompositionDraft.model_validate(page)
    assert complete_databases(draft_without, "Giúp mình lên kế hoạch cho thuê nhà") == draft_without
