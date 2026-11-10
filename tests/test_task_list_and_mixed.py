import asyncio

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from app.modules.modification_planner.services.database_rows import ROWS_AND_BLOCKS_MODEL
from app.modules.modification_planner.services.explicit_content import parse_explicit_blocks
from app.modules.modification_planner.services.explicit_plan import EXPLICIT_CONTENT_MODEL
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from scripts.evaluate_generation import CONTEXTS
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def answer(instruction: str, page: str):
    provider = FakeLLMProvider([])
    request = ModificationPlannerRequest(instruction=instruction, context=CONTEXTS[page])
    try:
        response = asyncio.run(ModificationPlannerService(provider).process(request))
    except Exception:
        return None, None
    return response, provider.calls


def blocks(plan) -> list[tuple[str, str]]:
    return [(block.type, block.content.text) for op in plan.operations
            if op.type == "INSERT_BLOCKS" for block in op.blocks]


@pytest.mark.parametrize(("instruction", "page", "expected", "after"), [
    ("add these tasks for recovery: Prepare post-run snacks and Join the Saturday group run "
     "after the Packing section", "trip",
     [("TODO", "Prepare post-run snacks"), ("TODO", "Join the Saturday group run")], "e2"),
    ("add these tasks: Book a physio session and Join the Saturday group run", "trip",
     [("TODO", "Book a physio session"), ("TODO", "Join the Saturday group run")], "e4"),
    ("add the following tasks: Book a physio session, Stretch for ten minutes at the end of the page", "trip",
     [("TODO", "Book a physio session"), ("TODO", "Stretch for ten minutes")], "e4"),
    ("thêm các việc sau: gọi khách, đặt phòng", "study", [("TODO", "Gọi khách"), ("TODO", "Đặt phòng")], None),
    ("them nhung viec sau: goi khach, dat phong", "study", [("TODO", "Goi khach"), ("TODO", "Dat phong")], None),
])
def test_these_tasks_are_a_todo_list(instruction, page, expected, after) -> None:
    response, calls = answer(instruction, page)
    assert calls == [] and response.model == EXPLICIT_CONTENT_MODEL
    assert blocks(response.result) == expected
    if after:
        assert response.result.operations[0].afterBlockId == after


@pytest.mark.parametrize("instruction", [
    "add these tasks",
    "add these tasks for recovery",
    "thêm các việc sau",
    "thêm việc sau buổi họp gọi khách",
])
def test_these_tasks_without_a_list_are_not_read_as_a_list(instruction) -> None:
    blocks_found = parse_explicit_blocks(instruction)
    assert blocks_found is None or len(blocks_found) == 1


@pytest.mark.parametrize(("instruction", "row", "header"), [
    ("thêm dòng Viết release note vào bảng Tasks và heading Tổng kết", "Viết release note", "Tổng kết"),
    ("add a row Write release notes to the Tasks table and a heading Wrap-up", "Write release notes", "Wrap-up"),
    ("them dong Viet release note vao bang Tasks va heading Tong ket", "Viet release note", "Tong ket"),
])
def test_a_row_and_a_heading_make_one_draft(instruction, row, header) -> None:
    response, calls = answer(instruction, "release")
    assert calls == [] and response.model == ROWS_AND_BLOCKS_MODEL
    operations = response.result.operations
    assert [op.type for op in operations] == ["CREATE_DATABASE_ROWS", "INSERT_BLOCKS"]
    assert [r.values for r in operations[0].rows] == [{"p-name": row}]
    assert blocks(response.result) == [("HEADER", header)]
    assert (operations[1].parentBlockId, operations[1].afterBlockId) == (None, "r1")


def test_a_row_and_a_todo_make_one_draft() -> None:
    response, calls = answer("add a row Smoke test to the Tasks table and a to-do Call the client", "release")
    assert calls == [] and response.model == ROWS_AND_BLOCKS_MODEL
    assert [r.values for r in response.result.operations[0].rows] == [{"p-name": "Smoke test"}]
    assert blocks(response.result) == [("TODO", "Call the client")]


def test_a_quoted_row_and_a_heading_make_one_draft() -> None:  # D-22
    response, calls = answer('thêm dòng "A và B" vào bảng Tasks và heading Tổng kết', "release")
    assert calls == [] and response.model == ROWS_AND_BLOCKS_MODEL
    assert [r.values for r in response.result.operations[0].rows] == [{"p-name": "A và B"}]
    assert blocks(response.result) == [("HEADER", "Tổng kết")]


def test_a_missing_table_is_no_mixed_draft() -> None:
    response, _ = answer("thêm dòng A dài vào bảng Không có và heading B", "release")
    assert response is None or response.model != ROWS_AND_BLOCKS_MODEL


def test_a_quoted_and_heading_is_no_mixed_draft() -> None:
    response, _ = answer('thêm dòng "Viết note và heading cuối" vào bảng Tasks', "release")
    assert response is not None and response.model != ROWS_AND_BLOCKS_MODEL
    assert all(op.type == "CREATE_DATABASE_ROWS" for op in response.result.operations)
