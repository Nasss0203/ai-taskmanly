import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_service import IntentService
from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from app.modules.page_composition.schemas.page_composition_schema import PageCompositionRequest
from app.modules.page_composition.services import PageCompositionService
from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest
from app.modules.page_intent.services.page_intent_service import PageIntentService
from app.modules.writing.schemas.writing_schema import WritingRequest
from app.modules.writing.services import WritingService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider
from tests.test_modification_planner_http import make_context


def request_payload(kind, text):
    if kind == "writing":
        return {"action": "IMPROVE", "text": text}
    if kind == "modification-planner":
        return {"instruction": text, "context": make_context()}
    return {"instruction": text}


REQUEST_MODELS = [
    ("intent", IntentRequest, 4000),
    ("writing", WritingRequest, 8000),
    ("page-composition", PageCompositionRequest, 4000),
    ("modification-planner", ModificationPlannerRequest, 4000),
    ("page-intent", PageIntentRequest, 4000),
]


@pytest.mark.parametrize("kind,model,limit", REQUEST_MODELS)
@pytest.mark.parametrize("text", ["Valid input", "MAX"])
def test_text_boundaries_are_preserved(kind, model, limit, text):
    text = "x" * limit if text == "MAX" else text
    result = model.model_validate(request_payload(kind, text))
    assert getattr(result, "text" if kind == "writing" else "instruction") == text


@pytest.mark.parametrize("kind,model,limit", REQUEST_MODELS)
@pytest.mark.parametrize("text", ["", " \t\n", "OVER"])
def test_invalid_text_is_rejected(kind, model, limit, text):
    text = "x" * (limit + 1) if text == "OVER" else text
    with pytest.raises(ValidationError):
        model.model_validate(request_payload(kind, text))


def nested_context(depth):
    result = "leaf"
    for _ in range(depth):
        result = {"nested": result}
    return result


def with_context(kind, bad_context):
    payload = request_payload(kind, "Add a note")
    if kind == "modification-planner":
        # These opaque fields are valid parts of AiPageContext. Test limits
        # rather than accidentally relying on a string field's type check.
        payload["context"]["blocks"] = [{
            "id": "block-1", "parentBlockId": None, "type": "TEXT",
            "orderIndex": 0, "title": None, "content": bad_context,
            "styleConfig": None, "dataConfig": None,
        }]
    else:
        payload["context"] = bad_context
    return payload


@pytest.mark.parametrize("kind,model,nodes", [
    ("page-composition", PageCompositionRequest, 1001),
    # Kế hoạch trang dài (E3): a Page context may hold 200 blocks.
    ("modification-planner", ModificationPlannerRequest, 8001),
])
@pytest.mark.parametrize("bad_context", [
    {"text": "x" * 8001}, nested_context(13), "nodes",
])
def test_structured_context_is_bounded(kind, model, nodes, bad_context):
    if bad_context == "nodes":
        bad_context = {"items": [None] * nodes}
    payload = with_context(kind, bad_context)
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_context_exact_byte_and_depth_boundaries():
    context = {"text": "x" * (8000 - len('{"text":""}'))}
    assert len(json.dumps(context, separators=(",", ":")).encode()) == 8000
    assert PageCompositionRequest(instruction="Add", context=context).context == context
    context["text"] += "x"
    with pytest.raises(ValidationError):
        PageCompositionRequest(instruction="Add", context=context)
    PageCompositionRequest(instruction="Add", context=nested_context(12))
    with pytest.raises(ValidationError):
        PageCompositionRequest(instruction="Add", context=nested_context(13))


def test_combined_instruction_context_budget():
    with pytest.raises(ValidationError):
        PageCompositionRequest(instruction="x" * 4000, context={"text": "x" * 7000})


@pytest.fixture
def secured_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("AI_INTERNAL_TOKEN", "test-token")
    provider = FakeLLMProvider([])
    with TestClient(app) as client:
        client.headers["X-Internal-Service-Token"] = "test-token"
        app.state.writing_service = WritingService(provider)
        app.state.page_composition_service = PageCompositionService(provider)
        app.state.modification_planner_service = ModificationPlannerService(provider)
        app.state.page_intent_service = PageIntentService(provider)
        app.state.intent_service = IntentService(provider)
        yield client, provider


@pytest.mark.parametrize("kind,model,limit", REQUEST_MODELS)
@pytest.mark.parametrize("text", ["", " \n\t", "OVER"])
def test_http_invalid_text_never_calls_llm(secured_client, kind, model, limit, text):
    client, provider = secured_client
    text = "x" * (limit + 1) if text == "OVER" else text
    response = client.post("/internal/v1/" + kind, json=request_payload(kind, text))
    assert response.status_code == 422
    assert provider.calls == []


@pytest.mark.parametrize("kind,nodes", [("page-composition", 1001), ("modification-planner", 8001)])
@pytest.mark.parametrize("bad_context", [
    {"text": "x" * 8001}, nested_context(13), "nodes",
])
def test_http_invalid_context_never_calls_llm(secured_client, kind, nodes, bad_context):
    if bad_context == "nodes":
        bad_context = {"items": [None] * nodes}
    client, provider = secured_client
    payload = with_context(kind, bad_context)
    assert client.post("/internal/v1/" + kind, json=payload).status_code == 422
    assert provider.calls == []


@pytest.mark.parametrize("kind,model,limit", REQUEST_MODELS)
@pytest.mark.parametrize("body", [
    '{"instruction":"Add","unused":"' + "x" * 65536 + '"}',
    '{"instruction":"Add","context":' + "[" * 1100 + "0" + "]" * 1100 + "}",
], ids=["oversized-body", "deep-json"])
def test_http_body_limits_before_json_parsing(secured_client, kind, model, limit, body):
    client, provider = secured_client
    response = client.post("/internal/v1/" + kind, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert provider.calls == []


def test_unicode_context_counts_utf8_bytes():
    with pytest.raises(ValidationError):
        PageCompositionRequest(instruction="Add", context={"text": "ế" * 3000})


def test_typed_planner_context_cannot_bypass_limits():
    from app.modules.modification_planner.schemas.modification_planner_schema import AiPageContext

    context = AiPageContext.model_validate(make_context())
    context.page.title = "x" * 8001
    with pytest.raises(ValidationError):
        ModificationPlannerRequest(instruction="Add", context=context)


def test_http_body_at_limit_and_brackets_in_strings(secured_client):
    client, provider = secured_client
    text = 'Read page "' + '[{\\"' * 50 + '"'
    provider._responses.append(json.dumps({
        "intent": "OTHER", "referenceType": "UNRESOLVED",
        "pageReference": None, "instruction": None, "needsClarification": False,
    }))
    body = json.dumps({"instruction": text}).encode()
    body += b" " * (65536 - len(body))
    response = client.post("/internal/v1/page-intent", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    assert len(provider.calls) == 1


@pytest.mark.parametrize("chunks,status", [
    ([b'{"instruction":"' + b"x" * 32768, b"x" * 32768 + b'"}'], 422),
    ([b'{"context":' + b"[" * 6, b"[" * 8 + b"0" + b"]" * 14 + b"}"], 422),
    ([b'{"instruction":"a\\', b'"[{}]"}'], 204),
], ids=["chunked-size", "chunked-depth", "chunked-escape"])
def test_stream_limits_without_content_length(chunks, status):
    import asyncio
    from app.api.request_limits import AIRequestLimitsMiddleware

    messages = iter({"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
                    for index, chunk in enumerate(chunks))
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        message = await receive()
        assert message["body"] == b"".join(chunks)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    asyncio.run(AIRequestLimitsMiddleware(downstream)(
        {"type": "http", "path": "/internal/v1/page-composition"}, receive, send,
    ))
    assert sent[0]["status"] == status


def planner_page(blocks: int, words: int = 12) -> dict:
    context = make_context()
    context["blocks"] = [{
        "id": f"00000000-0000-0000-0000-{i:012d}", "parentBlockId": None, "type": "TODO", "orderIndex": i,
        "title": None, "content": {"text": " ".join(["cập nhật báo cáo"] * (words // 3)), "checked": False},
        "styleConfig": None, "dataConfig": None,
    } for i in range(blocks)]
    context["completeness"]["blocks"] = {"total": blocks, "included": blocks, "truncated": False}
    return context


def test_planner_accepts_a_long_page():
    # E3: ~33 blocks were refused at 8000 bytes; the prompt now sends only what fits.
    # Within the 64 KB body limit a Page of typical text fits ~160–190 blocks.
    context = planner_page(150)
    assert len(json.dumps(context, ensure_ascii=False).encode()) > 8000
    ModificationPlannerRequest(instruction="thêm to-do A", context=context)


def test_planner_still_refuses_an_oversized_page_with_a_budget_message():
    with pytest.raises(ValidationError, match="exceeds the 56000-byte"):
        ModificationPlannerRequest(instruction="thêm to-do A", context=planner_page(200, words=60))
