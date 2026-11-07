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
