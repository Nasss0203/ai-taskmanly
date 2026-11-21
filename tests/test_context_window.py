import json
import uuid

from app.modules.modification_planner.schemas.modification_planner_schema import AiPageContext
from app.modules.modification_planner.services.context_window import window_context


def long_page(sections: int = 20, per_section: int = 8) -> AiPageContext:
    """sections × (1 HEADER + per_section TODO), plus a toggle with two children in section 3."""
    blocks, order = [], 0
    for s in range(1, sections + 1):
        blocks.append({"id": f"h{s}", "parentBlockId": None, "type": "HEADER", "orderIndex": order,
                       "title": None, "content": {"text": f"Phần {s}"}, "styleConfig": {"level": 2}, "dataConfig": None})
        order += 1
        for i in range(per_section):
            blocks.append({"id": f"t{s}-{i}", "parentBlockId": None, "type": "TODO", "orderIndex": order,
                           "title": None, "content": {"text": f"Việc {s}.{i} cần làm", "checked": False},
                           "styleConfig": None, "dataConfig": None})
            order += 1
        if s == 3:
            blocks.append({"id": "g3", "parentBlockId": None, "type": "TOGGLE", "orderIndex": order, "title": None,
                           "content": {"text": "Ghi chú phần 3"}, "styleConfig": None, "dataConfig": None})
            order += 1
            for c in range(2):
                blocks.append({"id": f"g3-{c}", "parentBlockId": "g3", "type": "TEXT", "orderIndex": c, "title": None,
                               "content": {"text": f"Ý {c}"}, "styleConfig": None, "dataConfig": None})
    return AiPageContext.model_validate({
        "schemaVersion": 1, "builtAt": "2026-11-06T00:00:00.000Z",
        "page": {"id": str(uuid.uuid4()), "workspaceId": "w", "teamspaceId": None, "parentPageId": None,
                 "title": "Trang dài", "icon": None, "coverUrl": None, "updatedAt": "2026-11-06T00:00:00.000Z"},
        "blocks": blocks, "databaseReferences": [], "databases": [],
        "completeness": {"blocks": {"total": len(blocks), "included": len(blocks), "truncated": False},
                         "databases": {"total": 0, "included": 0, "truncated": False}, "rows": [], "textTruncated": False},
    })


def ids(compact: dict) -> list[str]:
    return [block["id"] for block in compact["blocks"]]


def test_a_page_within_budget_is_sent_whole() -> None:
    page = long_page(sections=2, per_section=3)
    compact = window_context(page, "thêm to-do A", budget_tokens=100_000)
    assert len(compact["blocks"]) == len(page.blocks)
    assert "completeness" not in compact


def test_a_long_page_keeps_outline_and_tail_and_says_it_is_cut() -> None:
    page = long_page()
    compact = window_context(page, "thêm to-do Gọi khách hàng", budget_tokens=1_500)
    kept = ids(compact)
    assert [f"h{s}" for s in range(1, 21)] == [i for i in kept if i.startswith("h")]  # whole outline
    roots = [b.id for b in page.blocks if b.parentBlockId is None]
    assert set(roots[-3:]) <= set(kept)                                              # end of the page (shrinks to 3)
    assert "t5-3" not in kept                                                        # middle dropped
    assert compact["completeness"]["blocks"]["truncated"] is True
    assert compact["completeness"]["blocks"]["included"] == len(kept)
    assert kept == sorted(kept, key=[b.id for b in page.blocks].index)               # page order


def test_the_named_section_is_sent_whole() -> None:
    compact = window_context(long_page(), "thêm to-do Gọi khách hàng vào phần Phần 7", budget_tokens=1_500)
    assert {f"t7-{i}" for i in range(8)} <= set(ids(compact))


def test_a_named_block_and_its_toggle_are_sent() -> None:
    compact = window_context(long_page(), "thêm đoạn văn \"X\" sau dòng Ý 1", budget_tokens=1_500)
    assert {"g3", "g3-1"} <= set(ids(compact))


def test_a_section_with_a_toggle_keeps_its_children() -> None:
    compact = window_context(long_page(), "thêm to-do A vào phần Phần 3", budget_tokens=1_500)
    assert {"g3", "g3-0", "g3-1"} <= set(ids(compact))


def test_window_is_much_smaller_than_the_page() -> None:
    page = long_page()
    whole = window_context(page, "thêm to-do A", budget_tokens=100_000)
    cut = window_context(page, "thêm to-do A", budget_tokens=1_500)
    assert len(json.dumps(cut, ensure_ascii=False)) < 0.5 * len(json.dumps(whole, ensure_ascii=False))


def with_rows(page: AiPageContext, rows: int) -> AiPageContext:
    data = page.model_dump(mode="json", exclude_unset=True)
    data["blocks"].append({"id": "view", "parentBlockId": None, "type": "DATABASE_VIEW", "orderIndex": 999,
                           "title": None, "content": None, "styleConfig": None, "dataConfig": None})
    data["databaseReferences"] = [{"blockId": "view", "databaseId": "db", "viewId": "v"}]
    data["databases"] = [{"id": "db", "pageId": "p", "name": "Tasks", "properties": [
        {"id": "name", "name": "Tên", "type": "TITLE", "position": "0", "isDefault": True, "isHideable": False, "options": []}],
        "views": [{"id": "v", "databaseId": "db", "name": "Table", "type": "TABLE", "position": "0", "properties": []}],
        "rows": [{"id": f"r{i}", "databaseId": "db", "values": {"name": f"Dòng số {i} có tên khá dài"}} for i in range(rows)]}]
    data["completeness"]["databases"] = {"total": 1, "included": 1, "truncated": False}
    data["completeness"]["rows"] = [{"databaseId": "db", "total": rows, "included": rows, "truncated": False,
                                     "selection": "BOUNDED"}]
    return AiPageContext.model_validate(data)


def test_the_window_shrinks_to_its_budget() -> None:
    # E4 live run: outline + section + 10 tail blocks + a 10-row table reached ~4.240
    # tokens on a 160-block Page against a 2.800 budget.
    from app.modules.modification_planner.services.context_window import estimate_tokens

    page = with_rows(long_page(sections=20, per_section=8), rows=50)
    compact = window_context(page, "thêm to-do A vào phần Phần 7", budget_tokens=1_800)
    assert estimate_tokens(compact) <= 1_800
    kept = set(ids(compact))
    assert {f"h{s}" for s in range(1, 21)} <= kept and {f"t7-{i}" for i in range(8)} <= kept
    rows = compact["databases"][0]["rows"]
    assert len(rows) < 50
    assert compact["completeness"]["rows"][0] == {
        "databaseId": "db", "total": 50, "included": len(rows), "truncated": True, "selection": "BOUNDED"}
