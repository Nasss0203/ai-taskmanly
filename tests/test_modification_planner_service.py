from __future__ import annotations


import asyncio


import json


from copy import deepcopy


from typing import Any


import pytest


from pydantic import TypeAdapter


from app.core.exceptions import InvalidLLMResponseError


from app.llm.base import LLMGenerationResult, LLMTokenUsage


from app.modules.modification_planner.schemas.modification_planner_schema import (

    ChecklistInsertBlocksOperationBatch,

    ChecklistMixedModificationOperationBatch,

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


ROUTE_ADAPTER = TypeAdapter(ModificationPlannerRoute)


INSERT_BLOCKS_BATCH_ADAPTER = TypeAdapter(InsertBlocksOperationBatch)


CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER = TypeAdapter(

    ChecklistInsertBlocksOperationBatch,

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