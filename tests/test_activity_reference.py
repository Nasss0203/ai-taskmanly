"""M2 (kế hoạch tìm theo hoạt động, B1–B2): a Page named by the user's own edits."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.modules.page_intent.schemas.page_intent_schema import PageActivity, PageIntentRequest
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_intent.services.page_reference_evidence import (
    ActivityReference,
    activity_page_reference,
    detect_page_reference,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


TEST_TOKEN = "test-internal-service-token"


@pytest.mark.parametrize(("source", "instruction", "reference"), [
    ("thêm checklist gồm a, b vào trang tôi sửa gần đây nhất", "thêm checklist gồm a, b", ActivityReference("LATEST")),
    ("Tích gửi email trong trang tôi sửa hôm qua", "Tích gửi email", ActivityReference("YESTERDAY")),
    ("Thêm heading vào trang mình chỉnh 3 ngày trước", "Thêm heading", ActivityReference("N_DAYS_AGO", 3)),
    ("xoá Gửi email trong trang mà em sửa hôm kia", "xoá Gửi email", ActivityReference("N_DAYS_AGO", 2)),
    ("Thêm ghi chú vào trang release tôi sửa gần nhất", "Thêm ghi chú", ActivityReference("LATEST", None, "release")),
    ('thêm checklist vào trang "Kế hoạch Q4" mà tôi cập nhật hôm nay', "thêm checklist", ActivityReference("TODAY", None, "Kế hoạch Q4")),
    ("thêm checklist vào trang tôi sửa tuần trước.", "thêm checklist", ActivityReference("LAST_WEEK")),
    ("thêm checklist vào trang tôi chỉnh sửa gần đây nhé", "thêm checklist", ActivityReference("RECENT")),
    ("tích gửi email trong trang tôi vừa sửa", "tích gửi email", ActivityReference("LATEST")),
    ("Add a QA checklist to the page I edited yesterday", "Add a QA checklist", ActivityReference("YESTERDAY")),
    ("add notes to the release page I last edited", "add notes", ActivityReference("LATEST", None, "release")),
    ("add notes to the page that I updated 5 days ago", "add notes", ActivityReference("N_DAYS_AGO", 5)),
    ("add notes to the page I recently edited", "add notes", ActivityReference("RECENT")),
])
def test_recognises_a_page_named_by_my_edits(source, instruction, reference) -> None:
    assert activity_page_reference(source) == (instruction, reference)
    evidence = detect_page_reference(source)
    assert (evidence.reference_type, evidence.title, evidence.instruction, evidence.activity) == (
        "ACTIVITY", None, instruction, reference,
    )


@pytest.mark.parametrize("source", [
    # No time and no "vừa": which edit is meant is unclear.
    "thêm checklist vào trang tôi sửa",
    # Not an edit by the user.
    "thêm checklist vào trang tôi muốn",
    "thêm checklist vào trang của tôi",
    "thêm checklist vào trang An sửa hôm qua",
    # Out of range, or not a time.
    "thêm checklist vào trang tôi sửa 45 ngày trước",
    "thêm checklist vào trang tôi sửa sáng nay",
    # Creating a Page, or no edit clause.
    "tạo trang tôi sửa hôm qua",
    "xem trang tôi sửa hôm qua",
    # Two Pages.
    "chép từ trang sub man sang trang tôi sửa hôm qua",
    # A hint that is a whole sentence is not a name.
    "thêm checklist vào trang một hai ba bốn năm sáu tôi sửa hôm qua",
    "thêm checklist vào trang sub man",
])
def test_other_sentences_are_not_activity(source) -> None:
    assert activity_page_reference(source) is None
    assert detect_page_reference(source).reference_type != "ACTIVITY"


def test_page_intent_answers_without_the_model() -> None:
    provider = FakeLLMProvider([])
    response = asyncio.run(PageIntentService(provider).process(
        PageIntentRequest(instruction="Tích gửi email trong trang tôi sửa hôm qua"),
    ))
    assert provider.calls == []
    assert (response.provider, response.model) == ("deterministic", "activity-page-reference-v1")
    assert response.result.model_dump() == {
        "intent": "MODIFY_PAGE", "referenceType": "ACTIVITY", "pageReference": None,
        "instruction": "Tích gửi email", "needsClarification": False,
        "activity": {"relative": "YESTERDAY", "days": None, "titleHint": None},
    }


@pytest.mark.parametrize(("relative", "days"), [("N_DAYS_AGO", None), ("TODAY", 3), ("N_DAYS_AGO", 31)])
def test_only_n_days_ago_carries_days(relative, days) -> None:
    with pytest.raises(ValidationError):
        PageActivity.model_validate({"relative": relative, "days": days, "titleHint": None})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with TestClient(app) as test_client:
        yield test_client


def test_http_adds_the_activity_key_only_for_activity(client) -> None:
    """B2: NestJS checks the keys strictly; other results keep the five keys."""
    client.app.state.page_intent_service = PageIntentService(FakeLLMProvider([]))
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": "add notes to the release page I last edited"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == {
        "intent": "MODIFY_PAGE", "referenceType": "ACTIVITY", "pageReference": None,
        "instruction": "add notes", "needsClarification": False,
        "activity": {"relative": "LATEST", "days": None, "titleHint": "release"},
    }

    # Explicit title: answered by rules too, and still exactly five keys.
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": 'Thêm checklist vào page "Release 2.0", thêm mục Demo'},
    )
    assert response.status_code == 200
    assert sorted(response.json()["result"]) == [
        "instruction", "intent", "needsClarification", "pageReference", "referenceType",
    ]
