import asyncio

import pytest

from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services import intent_service as intent_module
from app.modules.intent.services.intent_service import IntentService
from app.modules.modification_planner.services.sentence_normalize import normalize_instruction, strip_polite
from app.modules.page_composition.schemas.page_composition_schema import PageCompositionRequest
from app.modules.page_composition.services.page_composition_service import PageCompositionService


class NoModel:
    provider_name = "none"
    model_name = "none"

    async def generate_json(self, *args, **kwargs):
        raise AssertionError("the rules must answer")

    async def generate(self, *args, **kwargs):
        raise AssertionError("the rules must answer")


@pytest.mark.parametrize("sentence, stripped", [
    ("bạn ơi trang Hội họp tuần còn việc nào chưa xong nha", "trang Hội họp tuần còn việc nào chưa xong"),
    ("nhờ bạn tóm tắt đoạn này nhé", "tóm tắt đoạn này"),
    ("bạn ơi, nhờ bạn tóm tắt đoạn này giúp mình", "tóm tắt đoạn này"),
    ('nhờ bạn dịch "giúp mình nhé" sang tiếng Anh', 'dịch "giúp mình nhé" sang tiếng Anh'),
    ("bạn tóm tắt đoạn này", "tóm tắt đoạn này"),
    ("bạn là ai", "bạn là ai"),
    ("tạo trang Ăn trưa gồm mua đồ ăn mang đi", "tạo trang Ăn trưa gồm mua đồ ăn mang đi"),
    ("viết thiệp cảm ơn", "viết thiệp cảm ơn"),
])
def test_polite_words_go_at_every_entrance(sentence: str, stripped: str) -> None:
    assert strip_polite(sentence) == stripped


def intent(sentence: str, selected: str | None = None):
    request = IntentRequest(instruction=sentence, selectedText=selected)
    return asyncio.run(IntentService(NoModel()).process(request)).result


def test_intent_rules_read_the_sentence_without_polite_words(monkeypatch) -> None:
    seen: list[str] = []
    original = intent_module.deterministic_result

    def spy(request: IntentRequest, *args, **kwargs):
        seen.append(request.instruction)
        return original(request, *args, **kwargs)

    monkeypatch.setattr(intent_module, "deterministic_result", spy)
    intent("bạn ơi trang Hội họp tuần còn việc nào chưa xong nha")
    assert seen[0] == "trang Hội họp tuần còn việc nào chưa xong"


@pytest.mark.parametrize("sentence", [
    "lập trang Dự án mới gồm có gọi khách, in hợp đồng và đặt vé",
    "cho mình lập trang Dự án mới gồm có gọi khách, in hợp đồng và đặt vé",
    "lap trang Du an moi gom co goi khach, in hop dong va dat ve",
])
def test_lap_trang_creates_a_page(sentence: str) -> None:
    assert intent(sentence).intent == "CREATE_PAGE"


def draft(sentence: str) -> dict:
    response = asyncio.run(PageCompositionService(NoModel()).process(PageCompositionRequest(instruction=sentence)))
    return response.result.model_dump(mode="json")


def todos(page: dict) -> list[str]:
    return [block["content"]["text"] for block in page["blocks"] if block["type"] == "TODO"]


@pytest.mark.parametrize("sentence", [
    "lập trang Dự án mới gồm có gọi khách, in hợp đồng và đặt vé",
    "cho mình lập trang Dự án mới gồm có gọi khách, in hợp đồng và đặt vé",
])
def test_lap_trang_with_gom_co_lists_the_items(sentence: str) -> None:
    page = draft(sentence)
    assert page["page"]["title"] == "Dự án mới"
    assert todos(page) == ["Gọi khách", "In hợp đồng", "Đặt vé"]


@pytest.mark.parametrize("tail", ["với", "nha", "giúp mình", "giùm"])
def test_polite_tail_after_the_last_item_is_not_an_item(tail: str) -> None:
    page = draft(f"tạo trang Tiệc cuối năm gồm in hợp đồng, đặt vé và ôn lại từ vựng {tail}")
    assert todos(page) == ["In hợp đồng", "Đặt vé", "Ôn lại từ vựng"]


def test_content_that_ends_like_a_tail_is_kept() -> None:
    assert normalize_instruction("tạo trang Ăn trưa gồm mua đồ ăn mang đi") == "tạo trang Ăn trưa gồm mua đồ ăn mang đi"
    assert normalize_instruction("thêm việc viết thiệp cảm ơn") == "thêm việc viết thiệp cảm ơn"
