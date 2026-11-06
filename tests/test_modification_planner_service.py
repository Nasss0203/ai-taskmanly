from __future__ import annotations


import asyncio


import json


from copy import deepcopy


from typing import Any


import pytest


from pydantic import TypeAdapter, ValidationError


from app.core.exceptions import InvalidLLMResponseError


from app.llm.base import LLMGenerationResult, LLMTokenUsage


from app.modules.modification_planner.schemas.modification_planner_schema import (

    ChecklistInsertBlocksOperationBatch,

    ChecklistMixedModificationOperationBatch,

    ChecklistWithHeadingInsertBlocksOperationBatch,

    CreateDatabaseRowsOperationBatch,

    InsertBlocksOperationBatch,

    MixedModificationOperationBatch,

    ModificationNeedMoreContextDetails,

    ModificationPlannerRequest,

    ModificationPlannerRoute,

)


from app.modules.modification_planner.services.modification_planner_service import (


    ModificationPlannerService,


)


from tests.fakes.fake_async_llm_provider import FakeLLMProvider

from app.modules.modification_planner.validators.modification_planner_semantic_validator import (
    ModificationPlannerSemanticValidationError,
)


@pytest.mark.parametrize("failure", ["route", "stage_two", "semantic"])
def test_invalid_response_logging_excludes_private_content(
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    private = "PRIVATE_VALIDATION_MARKER_FIX04B_73921"
    instruction = "PRIVATE_INSTRUCTION_FIX04B_73921"
    context_marker = "PRIVATE_PAGE_CONTEXT_FIX04B_73921"
    request = make_request(instruction)
    request.context.page.title = context_marker
    if failure == "route":
        route = make_route(private)
        with pytest.raises(ValidationError) as validation_error:
            ROUTE_ADAPTER.validate_python(route)
        assert private in str(validation_error.value)
        responses = [json.dumps(route)]
    else:
        batch = make_database_batch()
        if failure == "stage_two":
            batch["operations"][0]["rows"] = private
        else:
            batch["operations"][0]["databaseId"] = private
        responses = [
            json.dumps(make_route("CREATE_DATABASE_ROWS")),
            json.dumps(batch),
        ]
    provider = FakeLLMProvider(responses)
    with caplog.at_level("INFO"), pytest.raises(InvalidLLMResponseError) as error:
        asyncio.run(ModificationPlannerService(provider).process(request))

    cause = error.value.__cause__
    expected_type = (
        ModificationPlannerSemanticValidationError
        if failure == "semantic" else ValidationError
    )
    assert isinstance(cause, expected_type)
    assert private in str(cause)
    assert str(error.value) == "Modification planner response is invalid."
    assert len(provider.calls) == (1 if failure == "route" else 2)
    for sensitive in (private, instruction, context_marker):
        assert sensitive not in str(error.value)
        assert sensitive not in caplog.text
        for record in caplog.records:
            assert sensitive not in record.getMessage()
            assert sensitive not in repr(record.__dict__)
    assert "input_value" not in caplog.text
    assert str(cause) not in caplog.text
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == (
        "modification_planner_invalid_response provider=fake model=fake-model "
        f"error_type={expected_type.__name__}"
    )
    assert warnings[0].exc_info is None
    assert "modification_planner_succeeded" not in caplog.text


@pytest.mark.parametrize("stage", ["route", "stage_two"])
def test_provider_error_logging_excludes_private_message(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    from unittest.mock import AsyncMock
    from app.core.exceptions import LLMUnavailableError

    private = "PRIVATE_PROVIDER_ERROR_FIX04B_73921"
    failure = LLMUnavailableError(private)
    provider = FakeLLMProvider([])
    outcomes = [failure] if stage == "route" else [
        LLMGenerationResult(text=json.dumps(make_route("CREATE_DATABASE_ROWS"))),
        failure,
    ]
    generate = AsyncMock(side_effect=outcomes)
    monkeypatch.setattr(provider, "generate", generate)
    with caplog.at_level("INFO"), pytest.raises(LLMUnavailableError) as error:
        asyncio.run(ModificationPlannerService(provider).process(make_request()))
    assert error.value is failure
    assert generate.await_count == len(outcomes)
    assert private not in caplog.text
    for record in caplog.records:
        assert private not in repr(record.__dict__)
        assert record.exc_info is None
    assert "modification_planner_generation_failed" in caplog.text
    assert "provider=fake model=fake-model error_type=LLMUnavailableError" in caplog.text
    assert "modification_planner_succeeded" not in caplog.text


ROUTE_ADAPTER = TypeAdapter(ModificationPlannerRoute)


INSERT_BLOCKS_BATCH_ADAPTER = TypeAdapter(InsertBlocksOperationBatch)


CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER = TypeAdapter(

    ChecklistInsertBlocksOperationBatch,

)


CHECKLIST_WITH_HEADING_INSERT_BLOCKS_BATCH_ADAPTER = TypeAdapter(

    ChecklistWithHeadingInsertBlocksOperationBatch,

)


CREATE_DATABASE_ROWS_BATCH_ADAPTER = TypeAdapter(


    CreateDatabaseRowsOperationBatch,


)


MIXED_OPERATIONS_BATCH_ADAPTER = TypeAdapter(

    MixedModificationOperationBatch,

)


CHECKLIST_MIXED_OPERATIONS_BATCH_ADAPTER = TypeAdapter(

    ChecklistMixedModificationOperationBatch,

)


NEED_MORE_CONTEXT_DETAILS_ADAPTER = TypeAdapter(


    ModificationNeedMoreContextDetails,


)


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


        "blocks": [


            {


                "id": "block-header",


                "parentBlockId": None,


                "type": "HEADER",


                "orderIndex": 0,


                "title": None,


                "content": {


                    "text": "Release Plan",


                },


                "styleConfig": {


                    "level": 1,


                },


                "dataConfig": None,


            },


            {


                "id": "block-toggle",


                "parentBlockId": None,


                "type": "TOGGLE",


                "orderIndex": 1,


                "title": None,


                "content": {


                    "text": "Details",


                },


                "styleConfig": None,


                "dataConfig": None,


            },


            {


                "id": "block-child",


                "parentBlockId": "block-toggle",


                "type": "TEXT",


                "orderIndex": 0,


                "title": None,


                "content": {


                    "text": "Existing child",


                },


                "styleConfig": None,


                "dataConfig": None,


            },


            {


                "id": "block-database",


                "parentBlockId": None,


                "type": "DATABASE_VIEW",


                "orderIndex": 2,


                "title": None,


                "content": None,


                "styleConfig": None,


                "dataConfig": {


                    "database_id": "database-1",


                    "view_id": "view-1",


                },


            },


        ],


        "databaseReferences": [


            {


                "blockId": "block-database",


                "databaseId": "database-1",


                "viewId": "view-1",


            },


        ],


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


                    {


                        "id": "property-status",


                        "name": "Status",


                        "type": "STATUS",


                        "position": "1",


                        "isDefault": False,


                        "isHideable": True,


                        "options": [


                            {


                                "id": "option-todo",


                                "name": "Todo",


                                "color": "gray",


                                "position": "0",


                            },


                            {


                                "id": "option-done",


                                "name": "Done",


                                "color": "green",


                                "position": "1",


                            },


                        ],


                    },


                    {


                        "id": "property-priority",


                        "name": "Priority",


                        "type": "SELECT",


                        "position": "2",


                        "isDefault": False,


                        "isHideable": True,


                        "options": [


                            {


                                "id": "option-high",


                                "name": "High",


                                "color": "red",


                                "position": "0",


                            },


                        ],


                    },


                    {


                        "id": "property-points",


                        "name": "Story Points",


                        "type": "NUMBER",


                        "position": "3",


                        "isDefault": False,


                        "isHideable": True,


                        "options": [],


                    },


                ],


                "views": [


                    {


                        "id": "view-1",


                        "databaseId": "database-1",


                        "name": "Table",


                        "type": "TABLE",


                        "position": "0",


                        "properties": [],


                    },


                ],


                "rows": [


                    {


                        "id": "row-1",


                        "databaseId": "database-1",


                        "values": {


                            "property-title": "Existing task",


                            "property-status": "option-todo",


                        },


                    },


                ],


            },


        ],


        "completeness": {


            "blocks": {


                "total": 4,


                "included": 4,


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


                    "total": 1,


                    "included": 1,


                    "truncated": False,


                    "selection": "BOUNDED",


                },


            ],


            "textTruncated": False,


        },


    }


def make_ready_plan() -> dict[str, Any]:


    return {


        "schemaVersion": 1,


        "type": "AI_MODIFICATION_PLAN",


        "pageId": "page-1",


        "status": "PLAN_READY",


        "summary": "Add one release task and one checklist item.",


        "operations": [


            {


                "type": "CREATE_DATABASE_ROWS",


                "databaseId": "database-1",


                "rows": [


                    {


                        "values": {


                            "property-title": "Deploy release",


                            "property-status": "option-todo",


                            "property-priority": "option-high",


                            "property-points": 3,


                        },


                    },


                ],


            },


            {


                "type": "INSERT_BLOCKS",


                "parentBlockId": "block-toggle",


                "afterBlockId": "block-child",


                "blocks": [


                    {


                        "type": "TODO",


                        "content": {


                            "text": "Verify production deployment",


                            "checked": False,


                        },


                    },


                ],


            },


        ],


    }


def make_need_more_context_plan() -> dict[str, Any]:


    return {


        "schemaVersion": 1,


        "type": "AI_MODIFICATION_PLAN",


        "pageId": "page-1",


        "status": "NEED_MORE_CONTEXT",


        "summary": "The target is ambiguous.",


        "operations": [],


        "contextRequests": [


            {


                "reason": "AMBIGUOUS_TARGET",


                "description": "The requested target cannot be identified uniquely.",


                "question": "Which target should be modified?",


            },


        ],


    }


def make_request(


    instruction: str = "Add a release task.",


) -> ModificationPlannerRequest:


    return ModificationPlannerRequest.model_validate(


        {


            "instruction": instruction,


            "context": make_context(),


        },


    )


def make_route(


    *operation_types: str,


) -> dict[str, Any]:


    return {


        "status": "PLAN_READY",


        "operationTypes": list(operation_types),


    }


def make_need_more_context_route() -> dict[str, Any]:


    return {


        "status": "NEED_MORE_CONTEXT",


        "operationTypes": [],


    }


def make_mixed_batch() -> dict[str, Any]:


    plan = make_ready_plan()


    return {


        "createDatabaseRowsOperations": [


            plan["operations"][0],


        ],


        "insertBlocksOperations": [


            plan["operations"][1],


        ],


    }


def make_database_batch() -> dict[str, Any]:


    plan = make_ready_plan()


    return {


        "operations": [


            plan["operations"][0],


        ],


    }


def make_insert_batch() -> dict[str, Any]:


    plan = make_ready_plan()


    return {


        "operations": [


            plan["operations"][1],


        ],


    }


def make_need_more_context_details() -> dict[str, Any]:


    plan = make_need_more_context_plan()


    return {


        "summary": plan["summary"],


        "contextRequests": plan["contextRequests"],


    }


def test_modification_planner_returns_valid_mixed_ready_plan() -> None:


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_route(


                    "CREATE_DATABASE_ROWS",


                    "INSERT_BLOCKS",


                ),


                ensure_ascii=False,


            ),


            json.dumps(


                make_mixed_batch(),


                ensure_ascii=False,


            ),


        ],


    )


    request = make_request(


        (


            "Add a release task to the Tasks database "


            "and add a checklist item."


        ),


    )


    response = asyncio.run(


        ModificationPlannerService(provider).process(


            request,


        ),


    )


    assert response.provider == "fake"


    assert response.model == "fake-model"


    assert response.usage is None


    assert response.result.status == "PLAN_READY"


    assert response.result.pageId == "page-1"


    assert response.result.summary == request.instruction


    assert len(response.result.operations) == 2


    assert (


        response.result.operations[0].type


        == "CREATE_DATABASE_ROWS"


    )


    assert (


        response.result.operations[1].type


        == "INSERT_BLOCKS"


    )


    assert len(provider.calls) == 2


    assert provider.calls[0]["max_new_tokens"] == 256


    assert provider.calls[1]["max_new_tokens"] == 1200


    assert provider.calls[0]["response_schema"] == (


        ROUTE_ADAPTER.json_schema()


    )


    assert provider.calls[1]["response_schema"] == (

        CHECKLIST_MIXED_OPERATIONS_BATCH_ADAPTER.json_schema()

    )


    assert request.instruction in provider.calls[0]["user_prompt"]


    assert request.instruction in provider.calls[1]["user_prompt"]


    assert (


        '"id":"page-1"'


        in provider.calls[0]["user_prompt"]


    )


    assert (


        '"id":"page-1"'


        in provider.calls[1]["user_prompt"]


    )



def test_modification_planner_uses_checklist_schema_for_todo_mixed_instruction() -> None:
    provider = FakeLLMProvider(
        [
            json.dumps(
                make_route(
                    "INSERT_BLOCKS",
                    "CREATE_DATABASE_ROWS",
                ),
                ensure_ascii=False,
            ),
            json.dumps(
                make_mixed_batch(),
                ensure_ascii=False,
            ),
        ],
    )

    request = make_request(
        (
            'Add a TODO block with text "Check release" '
            "and add a row to the Tasks database."
        ),
    )

    response = asyncio.run(
        ModificationPlannerService(provider).process(
            request,
        ),
    )

    assert response.result.status == "PLAN_READY"
    assert len(response.result.operations) == 2

    assert provider.calls[1]["response_schema"] == (
        CHECKLIST_MIXED_OPERATIONS_BATCH_ADAPTER.json_schema()
    )

    insert_operations = [
        operation
        for operation in response.result.operations
        if operation.type == "INSERT_BLOCKS"
    ]

    assert len(insert_operations) == 1
    assert insert_operations[0].blocks[0].type == "TODO"


def test_modification_planner_returns_valid_insert_blocks_plan() -> None:


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_route("INSERT_BLOCKS"),


                ensure_ascii=False,


            ),


            json.dumps(


                make_insert_batch(),


                ensure_ascii=False,


            ),


        ],


    )


    response = asyncio.run(


        ModificationPlannerService(provider).process(


            make_request(


                "Add a checklist item under Details.",


            ),


        ),


    )


    assert response.result.status == "PLAN_READY"


    assert len(response.result.operations) == 1


    assert response.result.operations[0].type == "INSERT_BLOCKS"


    assert len(provider.calls) == 2


    assert provider.calls[1]["response_schema"] == (

        CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER.json_schema()

    )


    assert (


        "Chỉ tạo batch INSERT_BLOCKS"


        in provider.calls[1]["user_prompt"]


    )


def test_modification_planner_returns_valid_create_database_rows_plan() -> None:


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_route("CREATE_DATABASE_ROWS"),


                ensure_ascii=False,


            ),


            json.dumps(


                make_database_batch(),


                ensure_ascii=False,


            ),


        ],


    )


    response = asyncio.run(


        ModificationPlannerService(provider).process(


            make_request(


                "Add a release task to the Tasks database.",


            ),


        ),


    )


    assert response.result.status == "PLAN_READY"


    assert len(response.result.operations) == 1


    assert (


        response.result.operations[0].type


        == "CREATE_DATABASE_ROWS"


    )


    assert len(provider.calls) == 2


    assert provider.calls[1]["response_schema"] == (


        CREATE_DATABASE_ROWS_BATCH_ADAPTER.json_schema()


    )


    assert (


        "Chỉ tạo batch CREATE_DATABASE_ROWS"


        in provider.calls[1]["user_prompt"]


    )


def test_modification_planner_returns_need_more_context() -> None:


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_need_more_context_route(),


                ensure_ascii=False,


            ),


            json.dumps(


                make_need_more_context_details(),


                ensure_ascii=False,


            ),


        ],


    )


    response = asyncio.run(


        ModificationPlannerService(provider).process(


            make_request(


                "Update the relevant section.",


            ),


        ),


    )


    assert response.result.status == "NEED_MORE_CONTEXT"


    if response.result.status != "NEED_MORE_CONTEXT":


        raise AssertionError(


            "Expected NEED_MORE_CONTEXT result",


        )


    assert response.result.operations == []


    assert len(response.result.contextRequests) == 1


    assert (


        response.result.contextRequests[0].reason


        == "AMBIGUOUS_TARGET"


    )


    assert len(provider.calls) == 2


    assert provider.calls[0]["response_schema"] == (


        ROUTE_ADAPTER.json_schema()


    )


    assert provider.calls[1]["response_schema"] == (


        NEED_MORE_CONTEXT_DETAILS_ADAPTER.json_schema()


    )


    assert (


        "Router đã quyết định NEED_MORE_CONTEXT."


        in provider.calls[1]["user_prompt"]


    )


def test_modification_planner_sums_usage_across_two_stages() -> None:


    provider = FakeLLMProvider(


        [


            LLMGenerationResult(


                text=json.dumps(


                    make_route("INSERT_BLOCKS"),


                    ensure_ascii=False,


                ),


                usage=LLMTokenUsage(


                    prompt_tokens=40,


                    completion_tokens=10,


                    total_tokens=50,


                ),


            ),


            LLMGenerationResult(


                text=json.dumps(


                    make_insert_batch(),


                    ensure_ascii=False,


                ),


                usage=LLMTokenUsage(


                    prompt_tokens=120,


                    completion_tokens=30,


                    total_tokens=150,


                ),


            ),


        ],


    )


    response = asyncio.run(


        ModificationPlannerService(provider).process(


            make_request(


                "Add a checklist item under Details.",


            ),


        ),


    )


    assert response.usage is not None


    assert response.usage.model_dump() == {


        "prompt_tokens": 160,


        "completion_tokens": 40,


        "total_tokens": 200,


    }


def test_modification_planner_omits_usage_when_stage_two_usage_is_missing() -> None:


    provider = FakeLLMProvider(


        [


            LLMGenerationResult(


                text=json.dumps(


                    make_route("INSERT_BLOCKS"),


                    ensure_ascii=False,


                ),


                usage=LLMTokenUsage(


                    prompt_tokens=40,


                    completion_tokens=10,


                    total_tokens=50,


                ),


            ),


            json.dumps(


                make_insert_batch(),


                ensure_ascii=False,


            ),


        ],


    )


    response = asyncio.run(


        ModificationPlannerService(provider).process(


            make_request(


                "Add a checklist item under Details.",


            ),


        ),


    )


    assert response.usage is None


    dumped = response.model_dump(


        exclude_unset=True,


    )


    assert "usage" not in dumped


def test_modification_planner_rejects_invalid_route_json() -> None:


    provider = FakeLLMProvider(


        [


            "This is not JSON",


        ],


    )


    with pytest.raises(InvalidLLMResponseError):


        asyncio.run(


            ModificationPlannerService(provider).process(


                make_request(),


            ),


        )


    assert len(provider.calls) == 1


    assert provider.calls[0]["response_schema"] == (


        ROUTE_ADAPTER.json_schema()


    )


def test_modification_planner_rejects_invalid_route_schema() -> None:


    provider = FakeLLMProvider(


        [


            json.dumps(


                {


                    "status": "PLAN_READY",


                    "operationTypes": [],


                },


                ensure_ascii=False,


            ),


        ],


    )


    with pytest.raises(InvalidLLMResponseError):


        asyncio.run(


            ModificationPlannerService(provider).process(


                make_request(),


            ),


        )


    assert len(provider.calls) == 1


def test_modification_planner_rejects_invalid_stage_two_json_without_repair() -> None:


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_route("INSERT_BLOCKS"),


                ensure_ascii=False,


            ),


            "Stage two response is not JSON",


        ],


    )


    with pytest.raises(InvalidLLMResponseError):


        asyncio.run(


            ModificationPlannerService(provider).process(


                make_request(


                    "Add a checklist item under Details.",


                ),


            ),


        )


    assert len(provider.calls) == 2


    assert provider.calls[1]["response_schema"] == (

        CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER.json_schema()

    )


def test_modification_planner_rejects_invalid_stage_two_schema_without_repair() -> None:


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_route("INSERT_BLOCKS"),


                ensure_ascii=False,


            ),


            json.dumps(


                {


                    "operations": [],


                },


                ensure_ascii=False,


            ),


        ],


    )


    with pytest.raises(InvalidLLMResponseError):


        asyncio.run(


            ModificationPlannerService(provider).process(


                make_request(


                    "Add a checklist item under Details.",


                ),


            ),


        )


    assert len(provider.calls) == 2


def test_modification_planner_rejects_semantically_invalid_stage_two_without_repair() -> None:


    batch = make_database_batch()


    batch["operations"][0]["databaseId"] = (


        "database-unknown"


    )


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_route("CREATE_DATABASE_ROWS"),


                ensure_ascii=False,


            ),


            json.dumps(


                batch,


                ensure_ascii=False,


            ),


        ],


    )


    with pytest.raises(InvalidLLMResponseError):


        asyncio.run(


            ModificationPlannerService(provider).process(


                make_request(


                    "Add a release task to the Tasks database.",


                ),


            ),


        )


    assert len(provider.calls) == 2


    assert provider.calls[1]["response_schema"] == (


        CREATE_DATABASE_ROWS_BATCH_ADAPTER.json_schema()


    )


def test_modification_planner_preserves_router_operation_type_order_for_mixed_plan() -> None:


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_route(


                    "INSERT_BLOCKS",


                    "CREATE_DATABASE_ROWS",


                ),


                ensure_ascii=False,


            ),


            json.dumps(


                make_mixed_batch(),


                ensure_ascii=False,


            ),


        ],


    )


    response = asyncio.run(


        ModificationPlannerService(provider).process(


            make_request(


                (


                    "Add a checklist item and add "


                    "a release task to the database."


                ),


            ),


        ),


    )


    assert response.result.status == "PLAN_READY"


    assert len(response.result.operations) == 2


    assert (


        response.result.operations[0].type


        == "INSERT_BLOCKS"


    )


    assert (


        response.result.operations[1].type


        == "CREATE_DATABASE_ROWS"


    )


def test_modification_planner_does_not_mutate_request_context() -> None:


    context = make_context()


    original_context = deepcopy(context)


    request = ModificationPlannerRequest.model_validate(


        {


            "instruction": (


                "Add a release task to the database "


                "and add a checklist item."


            ),


            "context": context,


        },


    )


    provider = FakeLLMProvider(


        [


            json.dumps(


                make_route(


                    "CREATE_DATABASE_ROWS",


                    "INSERT_BLOCKS",


                ),


                ensure_ascii=False,


            ),


            json.dumps(


                make_mixed_batch(),


                ensure_ascii=False,


            ),


        ],


    )


    asyncio.run(


        ModificationPlannerService(provider).process(


            request,


        ),


    )


    assert (


        request.context.model_dump(


            mode="json",


            exclude_unset=True,


        )


        == original_context


    )


def test_modification_planner_strips_list_markers_from_todo_text() -> None:
    # The model numbered TODO items ("1. ...") although blocks keep the order.
    batch = make_insert_batch()
    batch["operations"][0]["blocks"] = [
        {"type": "TODO", "content": {"text": "1. Verify production deployment", "checked": False}},
        {"type": "TODO", "content": {"text": "- Notify the team", "checked": False}},
    ]
    provider = FakeLLMProvider([
        json.dumps(make_route("INSERT_BLOCKS"), ensure_ascii=False),
        json.dumps(batch, ensure_ascii=False),
    ])
    response = asyncio.run(
        ModificationPlannerService(provider).process(
            make_request("Add a checklist item under Details."),
        ),
    )
    texts = [block.content["text"] if isinstance(block.content, dict) else block.content.text
             for block in response.result.operations[0].blocks]
    assert texts == ["Verify production deployment", "Notify the team"]


def test_modification_planner_reanchors_a_non_toggle_parent_after_that_block() -> None:
    # The model used a TEXT block as parent; the validator rejected it (HTTP 502).
    context = make_context()
    text_block = next(block for block in context["blocks"] if block["type"] != "TOGGLE")
    batch = make_insert_batch()
    batch["operations"][0]["parentBlockId"] = text_block["id"]
    batch["operations"][0]["afterBlockId"] = text_block["id"]
    provider = FakeLLMProvider([
        json.dumps(make_route("INSERT_BLOCKS"), ensure_ascii=False),
        json.dumps(batch, ensure_ascii=False),
    ])
    response = asyncio.run(
        ModificationPlannerService(provider).process(
            make_request("Add a checklist item under Details."),
        ),
    )
    operation = response.result.operations[0]
    assert operation.parentBlockId == text_block["parentBlockId"]
    assert operation.afterBlockId == text_block["id"]


def run_insert_plan(instruction: str, blocks: list[dict[str, Any]]):
    batch = make_insert_batch()
    # Root insert, as in the live gp06 output (parentBlockId must survive normalization).
    batch["operations"][0].update(parentBlockId=None, afterBlockId="block-toggle", blocks=blocks)
    provider = FakeLLMProvider([
        json.dumps(make_route("INSERT_BLOCKS"), ensure_ascii=False),
        json.dumps(batch, ensure_ascii=False),
    ])
    response = asyncio.run(ModificationPlannerService(provider).process(make_request(instruction)))
    return response, provider


HEADING_AND_CHECKLIST = "thêm heading Việc tuần sau và checklist gồm cập nhật báo cáo, gửi email"


def test_heading_and_checklist_keeps_the_heading(model_path) -> None:
    # gp06: the TODO-only checklist schema turned the requested heading into a TODO.
    response, provider = run_insert_plan(HEADING_AND_CHECKLIST, [
        {"type": "HEADER", "content": {"text": "Việc tuần sau"}, "styleConfig": {"level": 2}},
        {"type": "TODO", "content": {"text": "Cập nhật báo cáo", "checked": False}},
        {"type": "TODO", "content": {"text": "Gửi email", "checked": False}},
    ])
    assert [block.type for block in response.result.operations[0].blocks] == ["HEADER", "TODO", "TODO"]
    assert provider.calls[1]["response_schema"] == CHECKLIST_WITH_HEADING_INSERT_BLOCKS_BATCH_ADAPTER.json_schema()


def test_checklist_without_heading_still_requires_todo_only(model_path) -> None:
    _, provider = run_insert_plan("thêm checklist gồm cập nhật báo cáo", [
        {"type": "TODO", "content": {"text": "Cập nhật báo cáo", "checked": False}},
    ])
    assert provider.calls[1]["response_schema"] == CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER.json_schema()


def test_heading_and_checklist_still_rejects_toggle_items(model_path) -> None:
    with pytest.raises(InvalidLLMResponseError):
        run_insert_plan(HEADING_AND_CHECKLIST, [
            {"type": "HEADER", "content": {"text": "Việc tuần sau"}, "styleConfig": {"level": 2}},
            {"type": "TOGGLE", "content": {"text": "Cập nhật báo cáo"}},
        ])


def test_heading_and_checklist_turns_listed_items_into_todos() -> None:
    # Live gp06 output: the model rendered the listed checklist items as HEADER level 3.
    response, _ = run_insert_plan(HEADING_AND_CHECKLIST, [
        {"type": "HEADER", "content": {"text": "Việc tuần sau"}, "styleConfig": {"level": 2}},
        {"type": "HEADER", "content": {"text": "Cập nhật báo cáo"}, "styleConfig": {"level": 3}},
        {"type": "HEADER", "content": {"text": "2. Gửi email."}, "styleConfig": {"level": 3}},
    ])
    blocks = response.result.operations[0].blocks
    assert [block.type for block in blocks] == ["HEADER", "TODO", "TODO"]
    # Content lock (gp31/gp32): the items are the user's words, not the model's "2. Gửi email.".
    assert [block.content.text for block in blocks] == ["Việc tuần sau", "Cập nhật báo cáo", "Gửi email"]
    assert blocks[1].content.checked is False
    assert blocks[0].styleConfig.level == 2


def test_heading_and_checklist_splits_a_multiline_header_of_listed_items() -> None:
    # Live gp06 output (qwen3:4b-instruct, 2/3 runs): both items packed in one bulleted HEADER.
    response, _ = run_insert_plan(HEADING_AND_CHECKLIST, [
        {"type": "HEADER", "content": {"text": "Việc tuần sau"}, "styleConfig": {"level": 2}},
        {"type": "HEADER", "content": {"text": "• Cập nhật báo cáo\n• Gửi email"}, "styleConfig": {"level": 3}},
    ])
    blocks = response.result.operations[0].blocks
    assert [block.type for block in blocks] == ["HEADER", "TODO", "TODO"]
    assert [block.content.text for block in blocks] == ["Việc tuần sau", "Cập nhật báo cáo", "Gửi email"]


def test_checklist_splits_a_multiline_todo_of_listed_items() -> None:
    response, _ = run_insert_plan("thêm checklist gồm cập nhật báo cáo, gửi email", [
        {"type": "TODO", "content": {"text": "1. Cập nhật báo cáo\n2. Gửi email", "checked": False}},
    ])
    assert [block.content.text for block in response.result.operations[0].blocks] == [
        "Cập nhật báo cáo", "Gửi email",
    ]


def test_multiline_header_with_an_unlisted_line_is_kept() -> None:
    # The multiline split leaves this HEADER alone; the content lock then
    # rebuilds the blocks the sentence spells out.
    from app.modules.modification_planner.schemas.modification_planner_schema import AiModificationPlan

    plan = TypeAdapter(AiModificationPlan).validate_python({
        "schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": make_context()["page"]["id"],
        "status": "PLAN_READY", "summary": "s",
        "operations": [{"type": "INSERT_BLOCKS", "parentBlockId": None, "afterBlockId": "block-toggle", "blocks": [
            {"type": "HEADER", "content": {"text": "Việc tuần sau\n• Gửi email"}, "styleConfig": {"level": 2}},
            {"type": "TODO", "content": {"text": "Cập nhật báo cáo", "checked": False}},
        ]}],
    })
    kept = ModificationPlannerService._checklist_items_as_todos(plan, HEADING_AND_CHECKLIST)
    assert [block.type for block in kept.operations[0].blocks] == ["HEADER", "TODO"]
    response, _ = run_insert_plan(HEADING_AND_CHECKLIST, [
        {"type": "HEADER", "content": {"text": "Việc tuần sau\n• Gửi email"}, "styleConfig": {"level": 2}},
        {"type": "TODO", "content": {"text": "Cập nhật báo cáo", "checked": False}},
    ])
    assert [(block.type, block.content.text) for block in response.result.operations[0].blocks] == [
        ("HEADER", "Việc tuần sau"), ("TODO", "Cập nhật báo cáo"), ("TODO", "Gửi email"),
    ]


TOPIC_ONLY_STEPS = [
    {"type": "TODO", "content": {"text": "Ôn từ vựng", "checked": False}},
    {"type": "TODO", "content": {"text": "Luyện ngữ pháp", "checked": False}},
    {"type": "TODO", "content": {"text": "Luyện nghe và nói", "checked": False}},
]


@pytest.mark.parametrize(("instruction", "topic"), [
    ("thêm checklist ôn tập môn Anh", "Ôn tập môn Anh"),                   # gp16 live output
    ("hãy thêm checklist ôn tập môn Anh vào cuối trang nhé", "Ôn tập môn Anh"),
    ("thêm checklist ôn tập môn Anh vào trang Ôn thi cuối kỳ", "Ôn tập môn Anh"),
    ("add a checklist packing for the beach at the end of the page", "Packing for the beach"),
])
def test_topic_only_checklist_keeps_one_todo_named_by_the_user(instruction: str, topic: str) -> None:
    response, _ = run_insert_plan(instruction, TOPIC_ONLY_STEPS)
    assert [(block.type, block.content.text) for block in response.result.operations[0].blocks] == [("TODO", topic)]


@pytest.mark.parametrize("instruction", [
    "thêm checklist gồm ôn từ vựng, luyện ngữ pháp, luyện nghe và nói",   # listed items stay
    "thêm checklist ôn từ vựng, luyện ngữ pháp, luyện nghe và nói",
    "Add a checklist item under Details.",                                # position not cut cleanly: unsure
    "add a checklist how to cook pho",
])
def test_listed_or_mixed_checklists_are_not_collapsed(instruction: str) -> None:
    # "luyện nghe và nói" may be one item, so neither the topic rule nor the
    # content lock touches these: the model's three items stay.
    response, _ = run_insert_plan(instruction, [
        *([{"type": "HEADER", "content": {"text": "Môn Anh"}, "styleConfig": {"level": 2}}] if "heading" in instruction else []),
        *TOPIC_ONLY_STEPS,
    ])
    assert sum(block.type == "TODO" for block in response.result.operations[0].blocks) == 3


def test_topic_only_checklist_with_a_source_page_is_not_collapsed() -> None:
    # M8: "checklist các bug blocker dựa trên trang X" takes its items from the source.
    batch = make_insert_batch()
    batch["operations"][0].update(parentBlockId=None, afterBlockId="block-toggle", blocks=TOPIC_ONLY_STEPS)
    provider = FakeLLMProvider([
        json.dumps(make_route("INSERT_BLOCKS"), ensure_ascii=False),
        json.dumps(batch, ensure_ascii=False),
    ])
    request = ModificationPlannerRequest.model_validate({
        "instruction": "thêm checklist ôn tập dựa trên trang Tài liệu",
        "context": make_context(),
        "references": [{"label": "S1", "pageTitle": "Tài liệu",
                        "text": "Ôn từ vựng. Luyện ngữ pháp. Luyện nghe và nói."}],
    })
    response = asyncio.run(ModificationPlannerService(provider).process(request))
    assert len(response.result.operations[0].blocks) == 3


def run_trip_plan(instruction: str, after: str, blocks: list[dict[str, Any]]):
    from scripts.evaluate_generation import CONTEXTS

    batch = {"operations": [{"type": "INSERT_BLOCKS", "parentBlockId": None, "afterBlockId": after, "blocks": blocks}]}
    provider = FakeLLMProvider([
        json.dumps(make_route("INSERT_BLOCKS"), ensure_ascii=False),
        json.dumps(batch, ensure_ascii=False),
    ])
    request = ModificationPlannerRequest(instruction=instruction, context=CONTEXTS["trip"])
    return asyncio.run(ModificationPlannerService(provider).process(request))


def test_toggle_inserted_in_a_todo_list_becomes_a_todo() -> None:
    # Live gp22 output: "add Toothbrush to the Packing list" -> an empty TOGGLE after "Phone charger".
    response = run_trip_plan("add Toothbrush to the Packing list", "e2", [
        {"type": "TOGGLE", "content": {"text": "Toothbrush"}},
    ])
    block = response.result.operations[0].blocks[0]
    assert (block.type, block.content.text, block.content.checked) == ("TODO", "Toothbrush", False)


def test_toggle_after_a_text_block_stays_a_toggle() -> None:
    response = run_trip_plan("add a toggle Day 2 after Day 1", "e4", [
        {"type": "TOGGLE", "content": {"text": "Day 2"}},
    ])
    assert response.result.operations[0].blocks[0].type == "TOGGLE"


NAMED_CHECKLIST = "thêm checklist chuẩn bị họp gồm in tài liệu, đặt phòng, gửi lịch mời"


def test_named_checklist_drops_the_name_rendered_as_a_todo() -> None:
    # Live gp01 output (qwen3:4b-instruct, 1/8 runs): the checklist name became the first TODO.
    response, _ = run_insert_plan(NAMED_CHECKLIST, [
        {"type": "TODO", "content": {"text": "Chuẩn bị họp", "checked": False}},
        {"type": "TODO", "content": {"text": "In tài liệu", "checked": False}},
        {"type": "TODO", "content": {"text": "Đặt phòng", "checked": False}},
        {"type": "TODO", "content": {"text": "Gửi lịch mời", "checked": False}},
    ])
    blocks = response.result.operations[0].blocks
    assert [block.content.text for block in blocks] == ["In tài liệu", "Đặt phòng", "Gửi lịch mời"]


def test_named_checklist_lists_items_after_gom() -> None:
    assert ModificationPlannerService._listed_checklist_items(NAMED_CHECKLIST) == {
        "in tài liệu", "đặt phòng", "gửi lịch mời",
    }
    assert ModificationPlannerService._checklist_name(NAMED_CHECKLIST) == "chuẩn bị họp"


def test_named_checklist_turns_listed_header_items_into_todos() -> None:
    response, _ = run_insert_plan("thêm heading Họp và checklist chuẩn bị họp gồm in tài liệu, đặt phòng", [
        {"type": "HEADER", "content": {"text": "Họp"}, "styleConfig": {"level": 2}},
        {"type": "HEADER", "content": {"text": "In tài liệu"}, "styleConfig": {"level": 3}},
        {"type": "TODO", "content": {"text": "Đặt phòng", "checked": False}},
    ])
    assert [block.type for block in response.result.operations[0].blocks] == ["HEADER", "TODO", "TODO"]


def test_checklist_keeps_a_name_todo_when_it_is_also_listed() -> None:
    # "checklist gồm chuẩn bị họp, đặt phòng": no name, every item stays.
    response, _ = run_insert_plan("thêm checklist gồm chuẩn bị họp, đặt phòng", [
        {"type": "TODO", "content": {"text": "Chuẩn bị họp", "checked": False}},
        {"type": "TODO", "content": {"text": "Đặt phòng", "checked": False}},
    ])
    assert len(response.result.operations[0].blocks) == 2


def test_named_checklist_keeps_the_name_todo_when_it_is_the_only_item() -> None:
    plan = run_insert_plan(NAMED_CHECKLIST, [
        {"type": "TODO", "content": {"text": "Chuẩn bị họp", "checked": False}},
    ])[0].result
    # The name rule alone never empties the draft …
    assert len(ModificationPlannerService._drop_checklist_name_todo(plan, NAMED_CHECKLIST).operations[0].blocks) >= 1
    # … and the content lock puts back the three listed items.
    assert [block.content.text for block in plan.operations[0].blocks] == ["In tài liệu", "Đặt phòng", "Gửi lịch mời"]


@pytest.mark.parametrize(("instruction", "expected"), [
    # gp19: the model invented three to-dos for one; never the anchor's name.
    ("thêm to-do Ôn chương 4 ngay sau to-do Ôn chương 3", [("TODO", "Ôn chương 4")]),
    # D4: a heading with a topic-only checklist is the heading and one to-do.
    ("thêm heading Môn Anh và checklist ôn tập", [("HEADER", "Môn Anh"), ("TODO", "Ôn tập")]),
])
def test_content_lock_keeps_only_the_spelled_out_blocks(instruction: str, expected: list) -> None:
    response, _ = run_insert_plan(instruction, [
        *([{"type": "HEADER", "content": {"text": "Môn Anh"}, "styleConfig": {"level": 2}}] if "heading" in instruction else []),
        *TOPIC_ONLY_STEPS,
    ])
    assert [(block.type, block.content.text) for block in response.result.operations[0].blocks] == expected


def test_normalizers_keep_headers_without_style_config() -> None:
    # Re-validating a dumped plan must not send styleConfig=null back in.
    response, _ = run_insert_plan(HEADING_AND_CHECKLIST, [
        {"type": "HEADER", "content": {"text": "Việc tuần sau"}},
        {"type": "HEADER", "content": {"text": "Cập nhật báo cáo"}},
        {"type": "TODO", "content": {"text": "1. Gửi email", "checked": False}},
    ])
    blocks = response.result.operations[0].blocks
    assert [(block.type, block.content.text) for block in blocks] == [
        ("HEADER", "Việc tuần sau"), ("TODO", "Cập nhật báo cáo"), ("TODO", "Gửi email"),
    ]
