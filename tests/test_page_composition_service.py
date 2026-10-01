import asyncio
import json
from copy import deepcopy
from typing import Any

import pytest

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMGenerationResult, LLMTokenUsage
from app.modules.page_composition.schemas.page_composition_schema import (
    PageCompositionDraft,
    PageCompositionRequest,
)
from app.modules.page_composition.services import PageCompositionService
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def make_valid_draft() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "type": "PAGE_COMPOSITION",
        "page": {
            "title": "Sprint Planning",
        },
        "blocks": [
            {
                "ref": "header_main",
                "type": "HEADER",
                "content": {
                    "text": "Sprint Planning",
                },
                "styleConfig": {
                    "level": 1,
                },
            },
            {
                "ref": "todo_prepare",
                "type": "TODO",
                "content": {
                    "text": "Prepare API implementation",
                    "checked": False,
                },
            },
            {
                "ref": "database_view_tasks",
                "type": "DATABASE_VIEW",
                "databaseRef": "database_tasks",
                "viewRef": "view_table",
            },
        ],
        "databases": [
            {
                "ref": "database_tasks",
                "name": "Tasks",
                "properties": [
                    {
                        "ref": "property_name",
                        "name": "Name",
                        "type": "TITLE",
                    },
                    {
                        "ref": "property_status",
                        "name": "Status",
                        "type": "SELECT",
                        "options": [
                            {
                                "ref": "option_todo",
                                "name": "Todo",
                            },
                            {
                                "ref": "option_done",
                                "name": "Done",
                            },
                        ],
                    },
                    {
                        "ref": "property_estimate",
                        "name": "Estimate",
                        "type": "NUMBER",
                    },
                    {
                        "ref": "property_completed",
                        "name": "Completed",
                        "type": "CHECKBOX",
                    },
                    {
                        "ref": "property_due_date",
                        "name": "Due",
                        "type": "DATE",
                    },
                ],
                "views": [
                    {
                        "ref": "view_table",
                        "name": "Table",
                        "type": "TABLE",
                    },
                ],
                "rows": [
                    {
                        "ref": "row_1",
                        "values": {
                            "property_name": "Implement API",
                            "property_status": {
                                "optionRef": "option_todo",
                            },
                            "property_estimate": 5,
                            "property_completed": False,
                            "property_due_date": {
                                "start": "2026-10-05",
                            },
                        },
                    },
                ],
            },
        ],
    }


def test_page_composition_returns_valid_draft() -> None:
    draft = make_valid_draft()

    provider = FakeLLMProvider(
        [
            json.dumps(
                draft,
                ensure_ascii=False,
            )
        ]
    )

    service = PageCompositionService(provider)

    request = PageCompositionRequest(
        instruction="Tạo trang sprint planning có bảng task.",
        context={
            "workspaceName": "Taskmanly",
        },
    )

    response = asyncio.run(
        service.process(request)
    )

    assert response.provider == "fake"
    assert response.model == "fake-model"
    assert response.usage is None

    assert response.result.schemaVersion == 1
    assert response.result.type == "PAGE_COMPOSITION"
    assert response.result.page.title == "Sprint Planning"

    assert len(response.result.blocks) == 3
    assert len(response.result.databases) == 1

    database = response.result.databases[0]

    assert database.ref == "database_tasks"
    assert len(database.properties) == 5
    assert len(database.views) == 1
    assert len(database.rows) == 1

    assert len(provider.calls) == 1
    assert provider.calls[0]["max_new_tokens"] == 4000

    assert provider.calls[0]["response_schema"] == (
        PageCompositionDraft.model_json_schema()
    )

    assert (
        "Chỉ trả về đúng MỘT JSON object hợp lệ"
        in provider.calls[0]["system_prompt"]
    )

    assert (
        "Tạo trang sprint planning có bảng task."
        in provider.calls[0]["user_prompt"]
    )

    assert (
        '"workspaceName":"Taskmanly"'
        in provider.calls[0]["user_prompt"]
    )


def test_page_composition_preserves_usage() -> None:
    draft = make_valid_draft()

    provider = FakeLLMProvider(
        [
            LLMGenerationResult(
                text=json.dumps(
                    draft,
                    ensure_ascii=False,
                ),
                usage=LLMTokenUsage(
                    prompt_tokens=120,
                    completion_tokens=80,
                    total_tokens=200,
                ),
            )
        ]
    )

    response = asyncio.run(
        PageCompositionService(provider).process(
            PageCompositionRequest(
                instruction="Tạo trang quản lý task.",
            )
        )
    )

    assert response.usage is not None

    assert response.usage.model_dump() == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }


def test_page_composition_rejects_invalid_json() -> None:
    provider = FakeLLMProvider(
        [
            "This is not JSON",
        ]
    )

    service = PageCompositionService(provider)

    request = PageCompositionRequest(
        instruction="Tạo một trang project.",
    )

    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(
            service.process(request)
        )

    assert len(provider.calls) == 1


def test_page_composition_rejects_non_object_json() -> None:
    provider = FakeLLMProvider(
        [
            json.dumps(
                [
                    {
                        "type": "PAGE_COMPOSITION",
                    }
                ]
            )
        ]
    )

    service = PageCompositionService(provider)

    request = PageCompositionRequest(
        instruction="Tạo một trang project.",
    )

    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(
            service.process(request)
        )

    assert len(provider.calls) == 1


def test_page_composition_rejects_invalid_schema() -> None:
    draft = make_valid_draft()

    draft["schemaVersion"] = 2

    provider = FakeLLMProvider(
        [
            json.dumps(draft),
        ]
    )

    service = PageCompositionService(provider)

    request = PageCompositionRequest(
        instruction="Tạo một trang project.",
    )

    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(
            service.process(request)
        )

    assert len(provider.calls) == 1


def test_page_composition_rejects_more_than_one_database() -> None:
    draft = make_valid_draft()

    second_database = deepcopy(
        draft["databases"][0],
    )

    second_database["ref"] = "database_secondary"
    second_database["name"] = "Secondary Database"
    second_database["rows"] = []

    draft["databases"].append(
        second_database,
    )

    provider = FakeLLMProvider(
        [
            json.dumps(draft),
        ]
    )

    service = PageCompositionService(provider)

    request = PageCompositionRequest(
        instruction="Tạo hai database.",
    )

    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(
            service.process(request)
        )

    assert len(provider.calls) == 1


def test_page_composition_rejects_more_than_twenty_rows() -> None:
    draft = make_valid_draft()

    draft["databases"][0]["rows"] = [
        {
            "ref": f"row_{index}",
            "values": {
                "property_name": f"Task {index}",
            },
        }
        for index in range(1, 22)
    ]

    provider = FakeLLMProvider(
        [
            json.dumps(draft),
        ]
    )

    service = PageCompositionService(provider)

    request = PageCompositionRequest(
        instruction="Tạo bảng task.",
    )

    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(
            service.process(request)
        )

    assert len(provider.calls) == 1


def test_page_composition_repairs_semantically_invalid_draft() -> None:
    invalid_draft = make_valid_draft()

    invalid_draft["blocks"].append(
        {
            "ref": "database_view_invalid",
            "type": "DATABASE_VIEW",
            "databaseRef": "database_tasks",
            "viewRef": "view_missing",
        }
    )

    repaired_draft = make_valid_draft()

    provider = FakeLLMProvider(
        [
            json.dumps(
                invalid_draft,
                ensure_ascii=False,
            ),
            json.dumps(
                repaired_draft,
                ensure_ascii=False,
            ),
        ]
    )

    service = PageCompositionService(provider)

    request = PageCompositionRequest(
        instruction="Tạo trang sprint planning.",
    )

    response = asyncio.run(
        service.process(request)
    )

    assert response.result.page.title == "Sprint Planning"
    assert len(response.result.blocks) == 3
    assert len(response.result.databases) == 1

    assert len(provider.calls) == 2

    assert provider.calls[0]["response_schema"] == (
        PageCompositionDraft.model_json_schema()
    )

    assert provider.calls[1]["response_schema"] == (
        PageCompositionDraft.model_json_schema()
    )

    assert provider.calls[1]["max_new_tokens"] == 4000

    assert (
        "Page Composition Draft trước đó không hợp lệ."
        in provider.calls[1]["user_prompt"]
    )

    assert (
        "view_missing"
        in provider.calls[1]["user_prompt"]
    )

    assert (
        "Draft không hợp lệ cần sửa:"
        in provider.calls[1]["user_prompt"]
    )

    assert (
        "DATABASE_VIEW block"
        in provider.calls[1]["user_prompt"]
    )


def test_page_composition_rejects_draft_when_repair_is_still_invalid() -> None:
    invalid_draft = make_valid_draft()

    invalid_draft["blocks"].append(
        {
            "ref": "database_view_invalid",
            "type": "DATABASE_VIEW",
            "databaseRef": "database_tasks",
            "viewRef": "view_missing",
        }
    )

    still_invalid_draft = make_valid_draft()

    still_invalid_draft["blocks"].append(
        {
            "ref": "database_view_still_invalid",
            "type": "DATABASE_VIEW",
            "databaseRef": "database_tasks",
            "viewRef": "view_still_missing",
        }
    )

    provider = FakeLLMProvider(
        [
            json.dumps(
                invalid_draft,
                ensure_ascii=False,
            ),
            json.dumps(
                still_invalid_draft,
                ensure_ascii=False,
            ),
        ]
    )

    service = PageCompositionService(provider)

    request = PageCompositionRequest(
        instruction="Tạo trang sprint planning.",
    )

    with pytest.raises(InvalidLLMResponseError):
        asyncio.run(
            service.process(request)
        )

    assert len(provider.calls) == 2

    assert provider.calls[0]["response_schema"] == (
        PageCompositionDraft.model_json_schema()
    )

    assert provider.calls[1]["response_schema"] == (
        PageCompositionDraft.model_json_schema()
    )

    assert (
        "view_missing"
        in provider.calls[1]["user_prompt"]
    ) 
def test_page_composition_sums_usage_across_repair() -> None:
    invalid_draft = make_valid_draft()

    invalid_draft["blocks"].append(
        {
            "ref": "database_view_invalid",
            "type": "DATABASE_VIEW",
            "databaseRef": "database_tasks",
            "viewRef": "view_missing",
        }
    )

    repaired_draft = make_valid_draft()

    provider = FakeLLMProvider(
        [
            LLMGenerationResult(
                text=json.dumps(
                    invalid_draft,
                    ensure_ascii=False,
                ),
                usage=LLMTokenUsage(
                    prompt_tokens=100,
                    completion_tokens=40,
                    total_tokens=140,
                ),
            ),
            LLMGenerationResult(
                text=json.dumps(
                    repaired_draft,
                    ensure_ascii=False,
                ),
                usage=LLMTokenUsage(
                    prompt_tokens=200,
                    completion_tokens=60,
                    total_tokens=260,
                ),
            ),
        ]
    )

    response = asyncio.run(
        PageCompositionService(provider).process(
            PageCompositionRequest(
                instruction="Tạo trang sprint planning.",
            )
        )
    )

    assert len(provider.calls) == 2

    assert response.usage is not None

    assert response.usage.model_dump() == {
        "prompt_tokens": 300,
        "completion_tokens": 100,
        "total_tokens": 400,
    }