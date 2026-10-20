from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.llm.base import LLMGenerationResult, LLMTokenUsage
from app.main import app
from app.modules.modification_planner.services.modification_planner_service import (
    ModificationPlannerService,
)
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


TEST_TOKEN = "test-internal-service-token"


def make_context() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "builtAt": "2026-10-06T07:00:00.000Z",
        "page": {
            "id": "page-1",
            "workspaceId": "workspace-1",
            "teamspaceId": None,
            "parentPageId": None,
            "title": "Release Plan",
            "icon": None,
            "coverUrl": None,
            "updatedAt": "2026-10-06T06:00:00.000Z",
        },
        "blocks": [],
        "databaseReferences": [],
        "databases": [
            {
                "id": "database-1",
                "pageId": "page-1",
                "name": "Tasks",
                "properties": [
                    {
                        "id": "property-title",
                        "name": "Name",
                        "type": "TITLE",
                        "position": "0",
                        "isDefault": True,
                        "isHideable": False,
                        "options": [],
                    },
                ],
                "views": [],
                "rows": [],
            },
        ],
        "completeness": {
            "blocks": {
                "total": 0,
                "included": 0,
                "truncated": False,
            },
            "databases": {
                "total": 1,
                "included": 1,
                "truncated": False,
            },
            "rows": [
                {
                    "databaseId": "database-1",
                    "total": 0,
                    "included": 0,
                    "truncated": False,
                    "selection": "BOUNDED",
                },
            ],
            "textTruncated": False,
        },
    }


def make_plan() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "PLAN_READY",
        "summary": "Add a task and a note.",
        "operations": [
            {
                "type": "CREATE_DATABASE_ROWS",
                "databaseId": "database-1",
                "rows": [
                    {
                        "values": {
                            "property-title": None,
                        },
                    },
                ],
            },
            {
                "type": "INSERT_BLOCKS",
                "parentBlockId": None,
                "afterBlockId": None,
                "blocks": [
                    {
                        "type": "TEXT",
                        "content": {
                            "text": "Release note",
                        },
                    },
                ],
            },
        ],
    }


def make_route() -> dict[str, Any]:
    return {
        "status": "PLAN_READY",
        "operationTypes": [
            "CREATE_DATABASE_ROWS",
            "INSERT_BLOCKS",
        ],
    }


def make_mixed_batch() -> dict[str, Any]:
    plan = make_plan()

    return {
        "createDatabaseRowsOperations": [
            plan["operations"][0],
        ],
        "insertBlocksOperations": [
            plan["operations"][1],
        ],
    }


def make_request_payload() -> dict[str, Any]:
    return {
        "instruction": "Add a task and a release note.",
        "context": make_context(),
    }


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "APP_ENV",
        "test",
    )
    monkeypatch.setenv(
        "AI_INTERNAL_TOKEN",
        TEST_TOKEN,
    )
    monkeypatch.setenv(
        "LLM_PROVIDER",
        "ollama",
    )

    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {
            "X-Internal-Service-Token": "wrong-token",
        },
    ],
)
def test_modification_planner_requires_internal_token(
    client: TestClient,
    headers: dict[str, str],
) -> None:
    response = client.post(
        "/internal/v1/modification-planner",
        headers=headers,
        json=make_request_payload(),
    )

    assert response.status_code == 401


def test_modification_planner_returns_plan_and_preserves_nulls(
    client: TestClient,
) -> None:
    provider = FakeLLMProvider(
        [
            json.dumps(
                make_route(),
                ensure_ascii=False,
            ),
            json.dumps(
                make_mixed_batch(),
                ensure_ascii=False,
            ),
        ],
    )

    client.app.state.modification_planner_service = (
        ModificationPlannerService(
            provider,
        )
    )

    response = client.post(
        "/internal/v1/modification-planner",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json=make_request_payload(),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["provider"] == "fake"
    assert body["model"] == "fake-model"

    assert body["result"]["schemaVersion"] == 1
    assert body["result"]["type"] == "AI_MODIFICATION_PLAN"
    assert body["result"]["pageId"] == "page-1"
    assert body["result"]["status"] == "PLAN_READY"

    assert (
        body["result"]["summary"]
        == "Add a task and a release note."
    )

    create_rows = body["result"]["operations"][0]

    assert (
        create_rows["rows"][0]["values"]["property-title"]
        is None
    )

    insert_blocks = body["result"]["operations"][1]

    assert insert_blocks["parentBlockId"] is None
    assert insert_blocks["afterBlockId"] is None

    assert "usage" not in body

    assert len(provider.calls) == 2


def test_modification_planner_returns_usage(
    client: TestClient,
) -> None:
    provider = FakeLLMProvider(
        [
            LLMGenerationResult(
                text=json.dumps(
                    make_route(),
                    ensure_ascii=False,
                ),
                usage=LLMTokenUsage(
                    prompt_tokens=20,
                    completion_tokens=5,
                    total_tokens=25,
                ),
            ),
            LLMGenerationResult(
                text=json.dumps(
                    make_mixed_batch(),
                    ensure_ascii=False,
                ),
                usage=LLMTokenUsage(
                    prompt_tokens=100,
                    completion_tokens=35,
                    total_tokens=135,
                ),
            ),
        ],
    )

    client.app.state.modification_planner_service = (
        ModificationPlannerService(
            provider,
        )
    )

    response = client.post(
        "/internal/v1/modification-planner",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json=make_request_payload(),
    )

    assert response.status_code == 200

    assert response.json()["usage"] == {
        "prompt_tokens": 120,
        "completion_tokens": 40,
        "total_tokens": 160,
    }

    assert len(provider.calls) == 2


def test_modification_planner_rejects_empty_instruction(
    client: TestClient,
) -> None:
    payload = make_request_payload()

    payload["instruction"] = ""

    response = client.post(
        "/internal/v1/modification-planner",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json=payload,
    )

    assert response.status_code == 422


def test_modification_planner_rejects_missing_context(
    client: TestClient,
) -> None:
    response = client.post(
        "/internal/v1/modification-planner",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json={
            "instruction": "Add a task.",
        },
    )

    assert response.status_code == 422


def test_modification_planner_invalid_llm_output_returns_502(
    client: TestClient,
) -> None:
    provider = FakeLLMProvider(
        [
            "not valid json",
        ],
    )

    client.app.state.modification_planner_service = (
        ModificationPlannerService(
            provider,
        )
    )

    response = client.post(
        "/internal/v1/modification-planner",
        headers={
            "X-Internal-Service-Token": TEST_TOKEN,
        },
        json=make_request_payload(),
    )

    assert response.status_code == 502

    assert response.json() == {
        "detail": "AI provider returned an invalid response.",
    }

    assert len(provider.calls) == 1