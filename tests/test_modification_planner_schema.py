from __future__ import annotations



import pytest

from pydantic import TypeAdapter, ValidationError



from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    ChecklistInsertBlocksOperationBatch,
    ChecklistMixedModificationOperationBatch,
    CreateDatabaseRowsOperationBatch,
    InsertBlocksOperationBatch,
    MixedModificationOperationBatch,
    ModificationNeedMoreContextDetails,
    ModificationPlannerRequest,
    ModificationPlannerResponse,
    ModificationPlannerRoute,
)





plan_adapter = TypeAdapter(AiModificationPlan)





def make_context() -> dict:

    return {

        "schemaVersion": 1,

        "builtAt": "2026-10-05T10:00:00.000Z",

        "page": {

            "id": "page-1",

            "workspaceId": "workspace-1",

            "teamspaceId": None,

            "parentPageId": None,

            "title": "Release Plan",

            "icon": None,

            "coverUrl": None,

            "updatedAt": "2026-10-05T09:00:00.000Z",

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

                "id": "block-database",

                "parentBlockId": None,

                "type": "DATABASE_VIEW",

                "orderIndex": 1,

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

                        ],

                    },

                    {

                        "id": "property-created-time",

                        "name": "Created time",

                        "type": "CREATED_TIME",

                        "position": "2",

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

                "total": 2,

                "included": 2,

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





def make_ready_plan() -> dict:

    return {

        "schemaVersion": 1,

        "type": "AI_MODIFICATION_PLAN",

        "pageId": "page-1",

        "status": "PLAN_READY",

        "summary": "Add one task and one checklist block.",

        "operations": [

            {

                "type": "CREATE_DATABASE_ROWS",

                "databaseId": "database-1",

                "rows": [

                    {

                        "values": {

                            "property-title": "Deploy release",

                            "property-status": "option-todo",

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





def make_need_more_context_plan() -> dict:

    return {

        "schemaVersion": 1,

        "type": "AI_MODIFICATION_PLAN",

        "pageId": "page-1",

        "status": "NEED_MORE_CONTEXT",

        "summary": "More row context is required.",

        "operations": [],

        "contextRequests": [

            {

                "reason": "ROWS_TRUNCATED",

                "description": "More database rows are required.",

                "databaseId": "database-1",

            },

        ],

    }





def test_request_accepts_current_page_context() -> None:

    request = ModificationPlannerRequest.model_validate(

        {

            "instruction": "Add a release task.",

            "context": make_context(),

        },

    )



    assert request.instruction == "Add a release task."

    assert request.context.page.id == "page-1"



    # Input context is allowed to contain resource types that

    # Planner cannot create.

    assert request.context.blocks[1].type == "DATABASE_VIEW"

    assert (

        request.context.databases[0].properties[2].type

        == "CREATED_TIME"

    )





def test_request_rejects_blank_instruction() -> None:

    with pytest.raises(ValidationError):

        ModificationPlannerRequest.model_validate(

            {

                "instruction": "   ",

                "context": make_context(),

            },

        )





def test_schema_version_rejects_boolean_true() -> None:

    plan = make_ready_plan()



    plan["schemaVersion"] = True



    with pytest.raises(ValidationError):

        plan_adapter.validate_python(plan)





def test_plan_ready_accepts_both_supported_operations() -> None:

    result = plan_adapter.validate_python(

        make_ready_plan(),

    )



    assert result.status == "PLAN_READY"

    assert len(result.operations) == 2

    assert result.operations[0].type == "CREATE_DATABASE_ROWS"

    assert result.operations[1].type == "INSERT_BLOCKS"





def test_need_more_context_requires_empty_operations() -> None:

    plan = make_need_more_context_plan()



    plan["operations"] = [

        {

            "type": "INSERT_BLOCKS",

            "parentBlockId": None,

            "afterBlockId": None,

            "blocks": [

                {

                    "type": "TEXT",

                    "content": {

                        "text": "Must not be executable",

                    },

                },

            ],

        },

    ]



    with pytest.raises(ValidationError):

        plan_adapter.validate_python(plan)





def test_unknown_operation_field_is_rejected() -> None:

    plan = make_ready_plan()



    plan["operations"][0]["unexpectedField"] = "invalid"



    with pytest.raises(ValidationError):

        plan_adapter.validate_python(plan)





def test_insert_blocks_requires_anchor_fields_even_when_null() -> None:

    plan = make_ready_plan()



    insert_operation = plan["operations"][1]



    del insert_operation["afterBlockId"]



    with pytest.raises(ValidationError):

        plan_adapter.validate_python(plan)





def test_null_block_anchors_are_preserved_in_serialization() -> None:

    result = plan_adapter.validate_python(

        make_ready_plan(),

    )



    dumped = result.model_dump(

        exclude_unset=True,

    )



    insert_operation = dumped["operations"][1]



    assert "parentBlockId" in insert_operation

    assert insert_operation["parentBlockId"] is None



    assert "afterBlockId" in insert_operation

    assert insert_operation["afterBlockId"] is None





def test_explicit_null_optional_context_request_field_is_rejected() -> None:

    plan = make_need_more_context_plan()



    plan["contextRequests"][0]["blockId"] = None



    with pytest.raises(ValidationError):

        plan_adapter.validate_python(plan)





def test_omitted_optional_context_request_fields_stay_omitted() -> None:

    result = plan_adapter.validate_python(

        make_need_more_context_plan(),

    )



    dumped = result.model_dump(

        exclude_unset=True,

    )



    request = dumped["contextRequests"][0]



    assert request["databaseId"] == "database-1"

    assert "blockId" not in request

    assert "question" not in request





def test_null_row_value_is_preserved() -> None:

    plan = make_ready_plan()



    plan["operations"][0]["rows"][0]["values"][

        "property-status"

    ] = None



    result = plan_adapter.validate_python(plan)



    dumped = result.model_dump(

        exclude_unset=True,

    )



    values = dumped["operations"][0]["rows"][0]["values"]



    assert "property-status" in values

    assert values["property-status"] is None





def test_response_omits_usage_when_not_provided() -> None:

    response = ModificationPlannerResponse.model_validate(

        {

            "result": make_ready_plan(),

            "provider": "ollama",

            "model": "qwen3:4b-instruct",

        },

    )



    dumped = response.model_dump(

        exclude_unset=True,

    )



    assert "usage" not in dumped





def test_response_preserves_usage_when_provided() -> None:

    response = ModificationPlannerResponse.model_validate(

        {

            "result": make_ready_plan(),

            "provider": "ollama",

            "model": "qwen3:4b-instruct",

            "usage": {

                "prompt_tokens": 100,

                "completion_tokens": 50,

                "total_tokens": 150,

            },

        },

    )



    dumped = response.model_dump(

        exclude_unset=True,

    )



    assert dumped["usage"] == {

        "prompt_tokens": 100,

        "completion_tokens": 50,

        "total_tokens": 150,

    }





def test_request_accepts_null_option_color() -> None:

    context = make_context()



    context["databases"][0]["properties"][1]["options"][0][

        "color"

    ] = None



    request = ModificationPlannerRequest.model_validate(

        {

            "instruction": "Add a release task.",

            "context": context,

        },

    )



    option = request.context.databases[0].properties[1].options[0]



    assert option.color is None





def test_modification_planner_route_accepts_insert_blocks() -> None:

    route = ModificationPlannerRoute.model_validate(

        {

            "status": "PLAN_READY",

            "operationTypes": [

                "INSERT_BLOCKS",

            ],

        },

    )



    assert route.status == "PLAN_READY"

    assert route.operationTypes == [

        "INSERT_BLOCKS",

    ]





def test_modification_planner_route_accepts_multiple_operation_types() -> None:

    route = ModificationPlannerRoute.model_validate(

        {

            "status": "PLAN_READY",

            "operationTypes": [

                "CREATE_DATABASE_ROWS",

                "INSERT_BLOCKS",

            ],

        },

    )



    assert route.operationTypes == [

        "CREATE_DATABASE_ROWS",

        "INSERT_BLOCKS",

    ]





def test_modification_planner_route_accepts_need_more_context() -> None:

    route = ModificationPlannerRoute.model_validate(

        {

            "status": "NEED_MORE_CONTEXT",

            "operationTypes": [],

        },

    )



    assert route.status == "NEED_MORE_CONTEXT"

    assert route.operationTypes == []





def test_modification_planner_route_rejects_ready_without_operation() -> None:

    with pytest.raises(

        ValueError,

        match="PLAN_READY requires at least one operation type",

    ):

        ModificationPlannerRoute.model_validate(

            {

                "status": "PLAN_READY",

                "operationTypes": [],

            },

        )





def test_modification_planner_route_rejects_duplicate_operation_types() -> None:

    with pytest.raises(

        ValueError,

        match="operationTypes must not contain duplicates",

    ):

        ModificationPlannerRoute.model_validate(

            {

                "status": "PLAN_READY",

                "operationTypes": [

                    "INSERT_BLOCKS",

                    "INSERT_BLOCKS",

                ],

            },

        )





def test_modification_planner_route_rejects_operations_for_need_more_context() -> None:

    with pytest.raises(

        ValueError,

        match="NEED_MORE_CONTEXT must not contain operation types",

    ):

        ModificationPlannerRoute.model_validate(

            {

                "status": "NEED_MORE_CONTEXT",

                "operationTypes": [

                    "INSERT_BLOCKS",

                ],

            },

        )





def test_create_database_rows_operation_batch_accepts_operations() -> None:

    operation = make_ready_plan()["operations"][0]



    batch = CreateDatabaseRowsOperationBatch.model_validate(

        {

            "operations": [

                operation,

            ],

        },

    )



    assert len(batch.operations) == 1



    assert (

        batch.operations[0].type

        == "CREATE_DATABASE_ROWS"

    )



    assert (

        batch.operations[0].databaseId

        == "database-1"

    )





def test_create_database_rows_operation_batch_rejects_empty_operations() -> None:

    with pytest.raises(ValidationError):

        CreateDatabaseRowsOperationBatch.model_validate(

            {

                "operations": [],

            },

        )





def test_insert_blocks_operation_batch_accepts_operations() -> None:

    operation = make_ready_plan()["operations"][1]



    batch = InsertBlocksOperationBatch.model_validate(

        {

            "operations": [

                operation,

            ],

        },

    )



    assert len(batch.operations) == 1

    assert batch.operations[0].type == "INSERT_BLOCKS"

    assert batch.operations[0].parentBlockId is None

    assert batch.operations[0].afterBlockId is None





def test_insert_blocks_operation_batch_rejects_empty_operations() -> None:

    with pytest.raises(ValidationError):

        InsertBlocksOperationBatch.model_validate(

            {

                "operations": [],

            },

        )





def test_need_more_context_details_accepts_context_requests() -> None:

    plan = make_need_more_context_plan()



    details = ModificationNeedMoreContextDetails.model_validate(

        {

            "summary": plan["summary"],

            "contextRequests": plan["contextRequests"],

        },

    )



    assert (

        details.summary

        == "More row context is required."

    )



    assert len(details.contextRequests) == 1



    assert (

        details.contextRequests[0].reason

        == "ROWS_TRUNCATED"

    )





def test_need_more_context_details_rejects_empty_context_requests() -> None:

    with pytest.raises(ValidationError):

        ModificationNeedMoreContextDetails.model_validate(

            {

                "summary": "More context is required.",

                "contextRequests": [],

            },

        )





def test_mixed_modification_operation_batch_accepts_both_operation_types() -> None:

    plan = make_ready_plan()



    batch = MixedModificationOperationBatch.model_validate(

        {

            "createDatabaseRowsOperations": [

                plan["operations"][0],

            ],

            "insertBlocksOperations": [

                plan["operations"][1],

            ],

        },

    )



    assert len(batch.createDatabaseRowsOperations) == 1

    assert len(batch.insertBlocksOperations) == 1



    assert (

        batch.createDatabaseRowsOperations[0].type

        == "CREATE_DATABASE_ROWS"

    )



    assert (

        batch.insertBlocksOperations[0].type

        == "INSERT_BLOCKS"

    )





def test_mixed_modification_operation_batch_rejects_empty_database_operations() -> None:

    plan = make_ready_plan()



    with pytest.raises(ValidationError):

        MixedModificationOperationBatch.model_validate(

            {

                "createDatabaseRowsOperations": [],

                "insertBlocksOperations": [

                    plan["operations"][1],

                ],

            },

        )





def test_mixed_modification_operation_batch_rejects_empty_insert_operations() -> None:

    plan = make_ready_plan()



    with pytest.raises(ValidationError):

        MixedModificationOperationBatch.model_validate(

            {

                "createDatabaseRowsOperations": [

                    plan["operations"][0],

                ],

                "insertBlocksOperations": [],

            },

        )

def test_checklist_insert_blocks_batch_accepts_todo_only() -> None:
    batch = ChecklistInsertBlocksOperationBatch.model_validate(
        {
            "operations": [
                {
                    "type": "INSERT_BLOCKS",
                    "parentBlockId": None,
                    "afterBlockId": None,
                    "blocks": [
                        {
                            "type": "TODO",
                            "content": {
                                "text": "Chuẩn bị release",
                                "checked": False,
                            },
                        },
                    ],
                },
            ],
        },
    )

    assert len(batch.operations) == 1
    assert batch.operations[0].type == "INSERT_BLOCKS"
    assert batch.operations[0].parentBlockId is None
    assert batch.operations[0].afterBlockId is None
    assert len(batch.operations[0].blocks) == 1
    assert batch.operations[0].blocks[0].type == "TODO"


def test_checklist_insert_blocks_batch_rejects_toggle() -> None:
    with pytest.raises(ValidationError):
        ChecklistInsertBlocksOperationBatch.model_validate(
            {
                "operations": [
                    {
                        "type": "INSERT_BLOCKS",
                        "parentBlockId": None,
                        "afterBlockId": None,
                        "blocks": [
                            {
                                "type": "TOGGLE",
                                "content": {
                                    "text": "Checklist chuẩn bị release",
                                },
                            },
                        ],
                    },
                ],
            },
        )


def test_checklist_mixed_batch_accepts_database_rows_and_todo() -> None:
    plan = make_ready_plan()

    batch = ChecklistMixedModificationOperationBatch.model_validate(
        {
            "createDatabaseRowsOperations": [
                plan["operations"][0],
            ],
            "insertBlocksOperations": [
                {
                    "type": "INSERT_BLOCKS",
                    "parentBlockId": None,
                    "afterBlockId": None,
                    "blocks": [
                        {
                            "type": "TODO",
                            "content": {
                                "text": "Chuẩn bị release",
                                "checked": False,
                            },
                        },
                    ],
                },
            ],
        },
    )

    assert len(batch.createDatabaseRowsOperations) == 1
    assert len(batch.insertBlocksOperations) == 1

    assert (
        batch.createDatabaseRowsOperations[0].type
        == "CREATE_DATABASE_ROWS"
    )

    assert (
        batch.insertBlocksOperations[0].blocks[0].type
        == "TODO"
    )


def test_checklist_mixed_batch_rejects_toggle() -> None:
    plan = make_ready_plan()

    with pytest.raises(ValidationError):
        ChecklistMixedModificationOperationBatch.model_validate(
            {
                "createDatabaseRowsOperations": [
                    plan["operations"][0],
                ],
                "insertBlocksOperations": [
                    {
                        "type": "INSERT_BLOCKS",
                        "parentBlockId": None,
                        "afterBlockId": None,
                        "blocks": [
                            {
                                "type": "TOGGLE",
                                "content": {
                                    "text": "Checklist chuẩn bị release",
                                },
                            },
                        ],
                    },
                ],
            },
        )

