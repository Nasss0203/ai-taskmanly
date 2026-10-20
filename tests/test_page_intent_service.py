import asyncio
import json

import pytest
from pydantic import ValidationError

from app.core.exceptions import InvalidLLMResponseError
from app.modules.page_intent.schemas.page_intent_schema import (
    PageIntentExtraction,
    PageIntentRequest,
)
from app.modules.page_intent.services.page_intent_service import PageIntentService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def result(
    *,
    intent="MODIFY_PAGE",
    reference_type="TITLE",
    page_reference="Release 2.0",
    instruction="Thêm heading Sprint Goal",
    needs_clarification=False,
):
    return {
        "intent": intent,
        "referenceType": reference_type,
        "pageReference": page_reference,
        "instruction": instruction,
        "needsClarification": needs_clarification,
    }


@pytest.mark.parametrize(
    "text,extraction",
    [
        ("Thêm heading Sprint Goal vào page Release 2.0", result()),
        (
            "Thêm checklist QA vào page này",
            result(
                reference_type="CURRENT_PAGE",
                page_reference=None,
                instruction="Thêm checklist QA",
            ),
        ),
        (
            'Thêm checklist vào trang "Kế hoạch phát hành"',
            result(
                page_reference="Kế hoạch phát hành",
                instruction="Thêm checklist",
            ),
        ),
        (
            "Thêm checklist vào page tôi sửa hôm qua",
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Thêm checklist",
                needs_clarification=True,
            ),
        ),
        (
            "Thêm checklist vào trang nói về OAuth",
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Thêm checklist",
                needs_clarification=True,
            ),
        ),
        (
            "Thêm checklist vào trang A hoặc trang B",
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Thêm checklist",
                needs_clarification=True,
            ),
        ),
        (
            "Tạo page Release 2.0",
            result(
                intent="OTHER",
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction=None,
            ),
        ),
        (
            "Viết lại văn bản này",
            result(
                intent="OTHER",
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction=None,
            ),
        ),
        (
            "Chưa rõ yêu cầu",
            result(
                intent="UNCLEAR",
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction=None,
                needs_clarification=True,
            ),
        ),
    ],
)
def test_valid_extraction(text, extraction):
    provider = FakeLLMProvider([json.dumps(extraction, ensure_ascii=False)])
    output = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=text)))
    assert output.result.model_dump() == extraction
    from app.modules.page_intent.services.page_reference_evidence import explicit_trailing_page_edit
    if explicit_trailing_page_edit(text) is not None:
        assert output.provider == "deterministic"
        assert output.model == "explicit-page-reference-v1"
        assert provider.calls == []
        return
    assert output.provider == "fake"
    assert output.model == "fake-model"
    assert len(provider.calls) == 1
    assert provider.calls[0]["user_prompt"] == text
    assert "pageId" in provider.calls[0]["system_prompt"]
    assert provider.calls[0]["response_schema"]


@pytest.mark.parametrize(
    "text,extraction",
    [
        ("Thêm vào page Release 2.0", result(page_reference="Invented")),
        ("Thêm vào page Release 2.0", {**result(), "pageId": "fake-id"}),
        ("Thêm vào page Release 2.0", result(reference_type="TITLE", page_reference=None)),
        ("Tạo page Release 2.0", result(intent="OTHER")),
        ("Thêm vào page Release 2.0", {**result(), "needsClarification": "false"}),
        ("Thêm vào page Release 2.0", {**result(), "instruction": ""}),
        ("Thêm vào page Release 2.0", {k: v for k, v in result().items() if k != "intent"}),
    ],
)
def test_rejects_invalid_extraction(text, extraction):
    # Provide two answers because explicit-title mismatches are retried once.
    provider = FakeLLMProvider([json.dumps(extraction, ensure_ascii=False)] * 2)
    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=text)))


@pytest.mark.parametrize("raw", ["not-json", "[]", "null"])
def test_invalid_json(raw):
    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(
            PageIntentService(FakeLLMProvider([raw, raw])).process(
                PageIntentRequest(instruction="Thêm vào page Release 2.0")
            )
        )


def test_request_rejects_whitespace_and_extra_fields():
    for value in ("", "   ", "\t"):
        with pytest.raises(ValidationError):
            PageIntentRequest(instruction=value)
    with pytest.raises(ValidationError):
        PageIntentRequest(instruction="Hello", pageId="123")


def test_schema_rejects_missing_and_invalid_combinations():
    with pytest.raises(ValidationError):
        PageIntentExtraction.model_validate({**result(), "referenceType": "RANDOM"})
    with pytest.raises(ValidationError):
        PageIntentExtraction.model_validate({**result(), "needsClarification": True})


@pytest.mark.parametrize(
    "source,generated,expected",
    [
        (
            "Thêm một heading Sprint Goal và checklist QA vào page Release 2.0",
            result(
                instruction="Thêm heading Sprint Goal và checklist QA",
            ),
            result(instruction="Thêm một heading Sprint Goal và checklist QA"),
        ),
        (
            "Chỉnh heading trong trang Sprint Planning 2026",
            result(
                reference_type="CURRENT_PAGE",
                page_reference="Sprint Planning 2026",
                instruction="Chỉnh heading",
            ),
            result(
                reference_type="TITLE",
                page_reference="Sprint Planning 2026",
                instruction="Chỉnh heading",
            ),
        ),
        (
            "Thêm checklist vào trang nói về OAuth",
            result(
                page_reference="trang nói về OAuth",
                instruction="thêm checklist",
            ),
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Thêm checklist",
                needs_clarification=True,
            ),
        ),
        (
            "Thêm checklist vào trang Alpha hoặc trang Beta",
            result(
                reference_type="CURRENT_PAGE",
                page_reference="Alpha hoặc trang Beta",
                instruction="Thêm checklist",
            ),
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Thêm checklist",
                needs_clarification=True,
            ),
        ),
        (
            "Thêm checklist vào page",
            result(
                reference_type="CURRENT_PAGE",
                page_reference="/",
                instruction="Thêm checklist",
            ),
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Thêm checklist",
                needs_clarification=True,
            ),
        ),
        (
            "Thêm checklist QA",
            result(
                reference_type="CURRENT_PAGE",
                page_reference=None,
                instruction="Thêm checklist QA",
            ),
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Thêm checklist QA",
                needs_clarification=True,
            ),
        ),
        (
            "Thêm vào page Release 2.0",
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Thêm",
                needs_clarification=False,
            ),
            result(instruction="Thêm"),
        ),
        (
            "Tạo page Release 2.0",
            result(
                intent="OTHER",
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Tạo page",
            ),
            result(
                intent="OTHER",
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction=None,
            ),
        ),
        (
            "Page là gì?",
            result(
                intent="UNCLEAR",
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction=None,
                needs_clarification=True,
            ),
            result(
                intent="OTHER",
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction=None,
            ),
        ),
        (
            "Viết lại câu này cho ngắn gọn: chúng ta đang chuẩn bị release.",
            result(
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction="Viết lại câu này cho ngắn gọn: chúng ta đang chuẩn bị release",
                needs_clarification=True,
            ),
            result(
                intent="OTHER",
                reference_type="UNRESOLVED",
                page_reference=None,
                instruction=None,
            ),
        ),
    ],
)
def test_normalizes_safe_real_model_errors(source, generated, expected):
    provider = FakeLLMProvider([json.dumps(generated, ensure_ascii=False)])
    actual = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert actual.result.model_dump() == expected


def test_restores_truncated_suffix_only_from_explicit_source_title():
    source = "Thêm checklist QA vào page Phase3 E2E Duplicate f54fda01c7"
    bad = result(
        page_reference="Phase3 E2E Duplicate",
        instruction="Thêm checklist QA",
    )
    good = result(
        page_reference="Phase3 E2E Duplicate f54fda01c7",
        instruction="Thêm checklist QA",
    )
    provider = FakeLLMProvider([json.dumps(bad, ensure_ascii=False)])
    output = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert output.result.model_dump() == good
    assert len(provider.calls) == 1
    assert all(call["user_prompt"] == source for call in provider.calls)


def test_does_not_restore_partial_word_or_invented_title():
    source = "Thêm checklist QA vào page Phase3 E2E Duplicate f54fda01c7"
    for title in ("Phase3 E2E Duplic", "A totally different title"):
        provider = FakeLLMProvider([
            json.dumps(result(page_reference=title, instruction="Thêm checklist QA"))] * 2
        )
        with pytest.raises(InvalidLLMResponseError):
            asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))


def test_retry_still_fails_closed_on_two_mismatching_titles():
    source = "Thêm checklist QA vào page Phase3 E2E Duplicate f54fda01c7"
    bad = json.dumps(result(page_reference="invented"), ensure_ascii=False)
    provider = FakeLLMProvider([bad, bad])
    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert len(provider.calls) == 2


def test_does_not_retry_or_accept_hallucinated_page_id():
    source = "Thêm checklist QA vào page Release 2.0"
    provider = FakeLLMProvider([
        json.dumps({**result(instruction="Thêm checklist QA"), "pageId": "fabricated"}),
        json.dumps(result(instruction="Thêm checklist QA")),
    ])
    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert len(provider.calls) == 1


def test_invalid_json_retries_once_then_succeeds():
    source = "Thêm checklist QA vào page Release 2.0"
    good = result(instruction="Thêm checklist QA")
    provider = FakeLLMProvider(["nonsense", json.dumps(good, ensure_ascii=False)])
    output = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert output.result.model_dump() == good
    assert len(provider.calls) == 2


def test_inconsistent_other_reference_retries_but_does_not_guess_intent():
    source = "Thêm checklist QA vào page Release 2.0"
    bad = result(intent="OTHER", instruction=None)
    good = result(instruction="Thêm checklist QA")
    provider = FakeLLMProvider([
        json.dumps(bad, ensure_ascii=False),
        json.dumps(good, ensure_ascii=False),
    ])
    output = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert output.result.model_dump() == good
    assert len(provider.calls) == 2


def test_explicit_named_edit_skips_unreliable_model_and_preserves_title():
    source = 'Trong page tên "Release 2.0", hãy thêm checklist QA'
    provider = FakeLLMProvider([])
    actual = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert actual.result.intent == 'MODIFY_PAGE'
    assert actual.result.referenceType == 'TITLE'
    assert actual.result.pageReference == 'Release 2.0'
    assert actual.result.instruction == 'hãy thêm checklist QA'
    assert actual.provider == 'deterministic'
    assert provider.calls == []


@pytest.mark.parametrize("misclassified_intent", ["OTHER", "UNCLEAR"])
def test_source_backed_page_edit_survives_model_intent_misclassification(misclassified_intent):
    source = "Add one TEXT block to page Release 2.0"
    provider = FakeLLMProvider([
        json.dumps(result(
            intent=misclassified_intent,
            reference_type="UNRESOLVED",
            page_reference=None,
            instruction=None,
            needs_clarification=misclassified_intent == "UNCLEAR",
        ))
    ])
    actual = asyncio.run(PageIntentService(provider).process(PageIntentRequest(instruction=source)))
    assert actual.result.intent == "MODIFY_PAGE"
    assert actual.result.referenceType == "TITLE"
    assert actual.result.pageReference == "Release 2.0"
    assert actual.result.instruction == "Add one TEXT block"
    assert len(provider.calls) == 1
