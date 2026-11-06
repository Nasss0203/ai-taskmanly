import asyncio
import json

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from app.modules.modification_planner.services.explicit_content import mentions_position
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from scripts.evaluate_generation import CONTEXTS
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


@pytest.mark.parametrize("instruction", [
    "thêm checklist bao gồm mua bút, mua vở và in đề cương",           # gp33
    "thêm to-do Gọi cho khách sạn vào trang Trip to Hanoi",            # a Page target is no position
    "thêm heading Việc tuần sau",                                      # "sau" inside the content
    'thêm đoạn văn "Gặp nhau sau giờ học ở cổng trường"',              # place words inside quotes
    "add a todo Exchange money",
    "add a todo Exchange money on the Trip to Hanoi page",
])
def test_sentences_without_a_place(instruction: str) -> None:
    assert mentions_position(instruction, "Trip to Hanoi") is False


@pytest.mark.parametrize("instruction", [
    "thêm to-do Làm đề năm 2024 vào phần Môn Toán",
    "thêm to-do Ôn chương 4 ngay sau to-do Ôn chương 3",
    "thêm heading Kết luận ở cuối trang",
    "thêm đoạn văn \"Họp lúc 9h\" sau phần ghi chú",
    "thêm dòng \"Đề cương\" vào trong mục Tài liệu tham khảo",
    "add Toothbrush to the Packing list",
    "add a heading Budget at the end of the page",
    "add a quote \"x\" under the Itinerary heading",
    "add a paragraph \"Day 2\" after Day 1: Old Quarter walking tour",
    "thêm checklist gồm A, B ở đầu trang",
])
def test_sentences_with_a_place(instruction: str) -> None:
    assert mentions_position(instruction, "Trip to Hanoi") is True


def run(instruction: str, page: str, parent: str | None, after: str | None, blocks: list[dict], references=None):
    batch = {"operations": [{"type": "INSERT_BLOCKS", "parentBlockId": parent, "afterBlockId": after, "blocks": blocks}]}
    route = {"status": "PLAN_READY", "operationTypes": ["INSERT_BLOCKS"]}
    provider = FakeLLMProvider([json.dumps(route), json.dumps(batch, ensure_ascii=False)])
    request = ModificationPlannerRequest.model_validate({
        "instruction": instruction, "context": CONTEXTS[page], **({"references": references} if references else {}),
    })
    return asyncio.run(ModificationPlannerService(provider).process(request)).result


TODOS = [{"type": "TODO", "content": {"text": t, "checked": False}} for t in ("Mua bút", "Mua vở", "In đề cương")]


def test_no_place_goes_after_the_last_root_block() -> None:
    # E2E 2026-11-05: the model put a new checklist after "Passport", inside the Packing list.
    plan = run("thêm checklist bao gồm mua bút, mua vở và in đề cương", "trip", None, "e1", TODOS)
    assert (plan.operations[0].parentBlockId, plan.operations[0].afterBlockId) == (None, "e4")


def test_no_place_leaves_a_toggle_and_goes_to_the_root() -> None:
    plan = run("thêm heading Ghi chú cuối", "study", "s5", "s6", [{"type": "HEADER", "content": {"text": "Ghi chú cuối"}}])
    assert (plan.operations[0].parentBlockId, plan.operations[0].afterBlockId) == (None, "s5")


def test_a_named_place_keeps_the_model_position() -> None:
    plan = run("thêm to-do Làm đề năm 2024 vào phần Môn Toán", "study", None, "s2",
               [{"type": "TODO", "content": {"text": "Làm đề năm 2024", "checked": False}}])
    assert plan.operations[0].afterBlockId == "s2"


def test_a_source_page_keeps_the_model_position() -> None:
    plan = run("thêm checklist các mục chính dựa trên trang Tài liệu", "trip", None, "e1", TODOS,
               references=[{"label": "S1", "pageTitle": "Tài liệu", "text": "Mua bút. Mua vở. In đề cương."}])
    assert plan.operations[0].afterBlockId == "e1"
