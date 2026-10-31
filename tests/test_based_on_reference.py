"""M8 (kế hoạch ngữ cảnh RAG, I2, I4, I5): the source a draft is based on."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.modules.modification_planner.prompts.modification_planner_prompt import (
    REFERENCE_RULES,
    build_insert_blocks_generation_prompt,
)
from app.modules.modification_planner.schemas.modification_planner_schema import (
    ModificationPlannerRequest,
)
from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.page_intent.services.page_reference_evidence import based_on_reference
from tests.fakes.fake_async_llm_provider import FakeLLMProvider
from tests.test_modification_planner_schema import make_context


TEST_TOKEN = "test-internal-service-token"


@pytest.mark.parametrize(("source", "rest", "named"), [
    ("thêm checklist các bug blocker vào trang Release 2.0 dựa trên trang Bug tracker",
     "thêm checklist các bug blocker vào trang Release 2.0", "trang Bug tracker"),
    ("thêm mục rủi ro vào trang Release 2.0 dựa trên ghi chú QA gần đây nhé",
     "thêm mục rủi ro vào trang Release 2.0", "ghi chú QA gần đây"),
    ("thêm checklist vào trang Release 2.0, căn cứ vào biên bản họp tuần",
     "thêm checklist vào trang Release 2.0", "biên bản họp tuần"),
    ("thêm checklist vào trang Release 2.0 theo nội dung của trang Ghi chú QA",
     "thêm checklist vào trang Release 2.0", "trang Ghi chú QA"),
    ("add a summary to the Release 2.0 page based on the QA notes",
     "add a summary to the Release 2.0 page", "the QA notes"),
])
def test_recognises_the_source(source, rest, named) -> None:
    assert based_on_reference(source) == (rest, named)


@pytest.mark.parametrize("source", [
    "thêm checklist gồm a, b vào trang Release 2.0",
    # "tham khảo" as a noun: what follows is the target, not a source.
    "thêm mục tài liệu tham khảo vào trang Release 2.0",
    # "theo" alone is not a source ("theo dõi", "theo thứ tự").
    "thêm việc theo dõi lỗi vào trang Release 2.0",
])
def test_other_sentences_name_no_source(source) -> None:
    assert based_on_reference(source) is None


def titled(title: str, instruction: str) -> FakeLLMProvider:
    return FakeLLMProvider([json.dumps({
        "intent": "MODIFY_PAGE", "referenceType": "TITLE", "pageReference": title,
        "instruction": instruction, "needsClarification": False,
    })])


def run(instruction: str, provider=None):
    return asyncio.run(PageIntentService(provider or FakeLLMProvider([])).process(
        PageIntentRequest(instruction=instruction),
    ))


def test_the_rest_of_the_sentence_is_read_as_usual() -> None:
    provider = titled("Release 2.0", "thêm checklist các bug blocker")
    response = run("thêm checklist các bug blocker vào trang Release 2.0 dựa trên trang Bug tracker", provider)
    # The model only ever sees the sentence without its source.
    assert "Bug tracker" not in provider.calls[0]["user_prompt"]
    assert response.model_dump()["result"] == {
        "intent": "MODIFY_PAGE", "referenceType": "TITLE", "pageReference": "Release 2.0",
        "instruction": "thêm checklist các bug blocker", "needsClarification": False,
        "basedOn": "trang Bug tracker",
    }


def test_a_described_target_keeps_its_own_key_too() -> None:
    response = run("thêm checklist vào trang về kế hoạch phát hành dựa trên ghi chú QA")
    result = response.model_dump()["result"]
    assert (result["referenceType"], result["description"], result["basedOn"]) == (
        "DESCRIPTION", "kế hoạch phát hành", "ghi chú QA",
    )


def test_no_key_without_a_source() -> None:
    provider = titled("Release 2.0", "thêm checklist gồm a, b")
    result = run("thêm checklist gồm a, b vào trang Release 2.0", provider).model_dump()["result"]
    assert "basedOn" not in result


def test_no_source_on_a_request_that_edits_nothing() -> None:
    output = {
        "intent": "OTHER", "referenceType": "UNRESOLVED", "pageReference": None,
        "instruction": None, "needsClarification": False,
    }
    response = run("xem trang Release 2.0 dựa trên ghi chú QA", FakeLLMProvider([json.dumps(output)]))
    assert "basedOn" not in response.model_dump()["result"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with TestClient(app) as test_client:
        yield test_client


def test_http_puts_the_source_inside_result(client) -> None:
    client.app.state.page_intent_service = PageIntentService(FakeLLMProvider([]))
    response = client.post(
        "/internal/v1/page-intent",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
        json={"instruction": 'thêm checklist vào trang "Release 2.0" dựa trên ghi chú QA'},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"result", "provider", "model"}
    assert body["result"]["basedOn"] == "ghi chú QA"
    assert body["result"]["pageReference"] == "Release 2.0"


def planner_request(references):
    return {"instruction": "thêm checklist các bug blocker", "context": make_context(), "references": references}


def reference(label="S1", text="Ứng dụng bị crash khi tải ảnh lớn"):
    return {"label": label, "pageTitle": "Bug tracker", "text": text}


def test_planner_takes_read_only_references() -> None:
    request = ModificationPlannerRequest.model_validate(planner_request([reference(), reference("S2")]))
    assert [item.label for item in request.references] == ["S1", "S2"]


@pytest.mark.parametrize("references", [
    [reference(f"S{index}") for index in range(1, 10)],  # more than 8
    [reference(), reference()],  # labels repeat
    [reference(label="P1")],
    [reference(text="x" * 401)],
    [reference(f"S{index}", "ồ" * 130) for index in range(1, 9)],  # > 3000 bytes
    [{**reference(), "pageId": "other-page"}],  # never an ID
])
def test_planner_rejects_bad_references(references) -> None:
    with pytest.raises(ValidationError):
        ModificationPlannerRequest.model_validate(planner_request(references))


def test_prompt_shows_references_and_their_rules_only_when_present() -> None:
    _, without = build_insert_blocks_generation_prompt("thêm checklist", {"page": {}})
    _, with_references = build_insert_blocks_generation_prompt(
        "thêm checklist", {"page": {}}, [reference()],
    )
    assert "references" not in without
    assert "Ứng dụng bị crash khi tải ảnh lớn" in with_references
    assert all(rule in with_references for rule in REFERENCE_RULES)
