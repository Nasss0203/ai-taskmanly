import asyncio

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiPageContext,
    ModificationPlannerRequest,
)
from app.modules.modification_planner.services.missing_target import plan_missing_target
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from scripts.evaluate_generation import CONTEXTS
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def context(name: str, truncated: bool = False) -> AiPageContext:
    data = AiPageContext.model_validate(CONTEXTS[name]).model_dump(mode="json")
    if truncated:
        data["completeness"]["blocks"].update(total=99, truncated=True)
        data["completeness"]["databases"].update(total=9, truncated=True)
    return AiPageContext.model_validate(data)


@pytest.mark.parametrize(("instruction", "page", "missing"), [
    ("thêm to-do Ôn bài 5 vào phần Môn Sinh", "study", "Môn Sinh"),               # gp15
    ("add a todo Book hotel under the Accommodation section", "trip", "Accommodation"),  # gp25
    ("thêm dòng Mua sữa vào bảng Chi tiêu", "reading", "Chi tiêu"),               # gp29
    ("thêm task Viết báo cáo vào bảng Sprint với trạng thái Todo", "release", "Sprint"),
    ("add a row Rent to the Expenses table", "reading", "Expenses"),
    ("thêm dòng Mua sữa vào bảng Chi tiêu", "meeting", "Chi tiêu"),               # Page without databases
    ("thêm đoạn văn Ghi nhớ vào mục \"Môn Hoá\" trong trang Ôn thi cuối kỳ", "study", "Môn Hoá"),
    # prepare_dataset "missing_section": a position after a section the Page lacks.
    ("thêm checklist gồm Lắp máy in và Dán nhãn từng thùng sau mục Phụ lục", "study", "Phụ lục"),
    ("add a checklist after the Appendix section: Call references, Share feedback", "trip", "Appendix"),
])
def test_missing_section_or_table_is_asked_back(instruction: str, page: str, missing: str) -> None:
    plan = plan_missing_target(instruction, context(page))
    assert plan is not None
    assert plan.status == "NEED_MORE_CONTEXT"
    assert plan.operations == []
    assert plan.contextRequests[0].reason == "MISSING_RESOURCE_CONTEXT"
    assert f'"{missing}"' in plan.contextRequests[0].description


@pytest.mark.parametrize(("instruction", "page"), [
    ("thêm to-do Làm đề năm 2024 vào phần Môn Toán", "study"),           # gp10
    ("thêm to-do làm đề vào phần mon toan", "study"),                    # no Vietnamese marks
    ("thêm dòng \"Đề cương\" vào trong mục Tài liệu tham khảo", "study"),  # gp13, a toggle
    ("thêm đoạn văn \"Họp lúc 9h\" sau phần ghi chú", "meeting"),         # gp04, "sau" is a position
    ("thêm ghi chú vào phần ghi chú", "meeting"),                        # a TEXT "Ghi chú: …"
    ("add Toothbrush to the Packing list", "trip"),                      # gp22
    ("add a todo Book hotel under the Itinerary section", "trip"),
    ("thêm 2 dòng vào bảng Tasks: Viết release note, Kiểm thử hồi quy", "release"),  # gp07
    ("thêm sách Đắc nhân tâm vào bảng Sách với tình trạng Đang đọc", "reading"),    # gp27
    ("add Atomic Habits to the Sách table as Đã đọc", "reading"),          # gp30
    ("thêm bảng Chi tiêu", "reading"),                                    # creating a table, not a target
    ("thêm checklist ôn tập môn Anh", "study"),
    ("add a todo Book hotel after the Itinerary heading", "trip"),
    # Synthetic "mixed" sentence: the table exists, the heading is new.
    ("add a row Pho to the Sách table and a heading Wrap-up", "reading"),
])
def test_named_target_on_the_page_goes_to_the_planner(instruction: str, page: str) -> None:
    assert plan_missing_target(instruction, context(page)) is None


def test_truncated_context_is_never_called_missing() -> None:
    assert plan_missing_target("thêm to-do Ôn bài 5 vào phần Môn Sinh", context("study", truncated=True)) is None
    assert plan_missing_target("thêm dòng Mua sữa vào bảng Chi tiêu", context("reading", truncated=True)) is None


def test_service_asks_back_without_calling_the_model() -> None:
    provider = FakeLLMProvider([])
    request = ModificationPlannerRequest(
        instruction="thêm dòng Mua sữa vào bảng Chi tiêu", context=CONTEXTS["reading"],
    )
    response = asyncio.run(ModificationPlannerService(provider).process(request))
    assert response.result.status == "NEED_MORE_CONTEXT"
    assert response.provider == "rules"
    assert provider.calls == []
