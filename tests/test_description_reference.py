"""M6 (kế hoạch tìm theo mô tả, G1): a Page named by what it is for."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.modules.page_intent.schemas.page_intent_schema import (
    DescriptionPageIntent,
    PageIntentRequest,
)
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_intent.services.page_reference_evidence import (
    description_page_reference,
    detect_page_reference,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


TEST_TOKEN = "test-internal-service-token"


@pytest.mark.parametrize(("source", "instruction", "description"), [
    ("thêm checklist gồm a, b vào trang về kế hoạch marketing", "thêm checklist gồm a, b", "kế hoạch marketing"),
    ("Thêm mục họp vào trang ghi biên bản họp hằng tuần", "Thêm mục họp", "biên bản họp hằng tuần"),
    ("thêm việc gọi khách vào trang dùng để chuẩn bị phát hành sản phẩm nhé", "thêm việc gọi khách", "chuẩn bị phát hành sản phẩm"),
    ("Thêm checklist vào trang theo dõi lỗi ứng dụng.", "Thêm checklist", "lỗi ứng dụng"),
    # "của" belongs to the description here, not a place (M4).
    ("thêm việc kiểm tra vào trang theo dõi lỗi của ứng dụng", "thêm việc kiểm tra", "lỗi của ứng dụng"),
    ("thêm mục ngân sách vào trang nói về chuyến đi Đà Lạt", "thêm mục ngân sách", "chuyến đi Đà Lạt"),
    ("thêm ghi chú vào trang liên quan đến tuyển dụng nhân sự", "thêm ghi chú", "tuyển dụng nhân sự"),
    # Without marks the cues are unclear ("ve" is "về" or "vẽ"): left to the model.
    ("them checklist vao trang ve ke hoach marketing", None, None),
    # The edit after the description.
    ("Sửa trang dùng để chuẩn bị phát hành sản phẩm: thêm mục kiểm tra bản build", "thêm mục kiểm tra bản build", "chuẩn bị phát hành sản phẩm"),
    ("add a checklist to the page about onboarding new staff", "add a checklist", "onboarding new staff"),
    ("add a QA section to the page where we track app bugs", "add a QA section", "app bugs"),
    ("update the page about the Q4 marketing plan: add a budget row", "add a budget row", "the Q4 marketing plan"),
])
def test_recognises_a_described_page(source, instruction, description) -> None:
    expected = None if instruction is None else (instruction, description)
    assert description_page_reference(source) == expected
    if expected is not None:
        evidence = detect_page_reference(source)
        assert (evidence.reference_type, evidence.instruction, evidence.description) == (
            "DESCRIPTION", instruction, description,
        )


@pytest.mark.parametrize("source", [
    # A real-looking title: the name path handles it (G4).
    "thêm việc mua sữa vào trang công thức nấu ăn",
    # "ghi chú" (a note) is a word of its own, not "ghi" + a description.
    "thêm việc vào trang ghi chú công việc",
    # One word describes too little (G1).
    "thêm việc vào trang về nhà",
    # A quoted name is a title.
    'thêm việc vào trang "về kế hoạch marketing"',
    # M2 / M4 keep their own rules.
    "thêm checklist vào trang tôi sửa hôm qua",
    "thêm checklist vào trang Tasks trong trang Dự án A",
    # Two Pages.
    "chép việc từ trang về kế hoạch sang trang về ngân sách",
    # No edit, or not an edit.
    "Sửa trang dùng để chuẩn bị phát hành sản phẩm",
    "xem trang về kế hoạch marketing",
    "tạo trang về kế hoạch marketing",
])
def test_other_sentences_are_not_descriptions(source) -> None:
    assert description_page_reference(source) is None


def test_page_intent_answers_without_the_model() -> None:
    provider = FakeLLMProvider([])
    response = asyncio.run(PageIntentService(provider).process(
        PageIntentRequest(instruction="Thêm mục họp vào trang ghi biên bản họp hằng tuần"),
    ))
    assert provider.calls == []
    assert (response.provider, response.model) == ("deterministic", "description-page-reference-v1")
    assert response.result.model_dump() == {
        "intent": "MODIFY_PAGE", "referenceType": "DESCRIPTION", "pageReference": None,
        "instruction": "Thêm mục họp", "needsClarification": False,
        "description": "biên bản họp hằng tuần",
    }


@pytest.mark.parametrize("change", [
    {"pageReference": "Họp tuần"},
    {"needsClarification": True},
    {"description": ""},
    {"description": None},
])
def test_a_description_result_is_strict(change) -> None:
    valid = {
        "intent": "MODIFY_PAGE", "referenceType": "DESCRIPTION", "pageReference": None,
        "instruction": "Thêm mục họp", "needsClarification": False,
        "description": "biên bản họp hằng tuần",
    }
    with pytest.raises(ValidationError):
        DescriptionPageIntent.model_validate({**valid, **change})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with TestClient(app) as test_client:
        yield test_client


def test_http_adds_the_description_key_only_for_a_description(client) -> None:
    """NestJS checks keys strictly; other results keep their keys."""
    client.app.state.page_intent_service = PageIntentService(FakeLLMProvider([]))
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": "add a checklist to the page about onboarding new staff"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == {
        "intent": "MODIFY_PAGE", "referenceType": "DESCRIPTION", "pageReference": None,
        "instruction": "add a checklist", "needsClarification": False,
        "description": "onboarding new staff",
    }
