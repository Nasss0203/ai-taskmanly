from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import TypeAdapter

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    AiPageContext,
)
from app.modules.modification_planner.validators.modification_planner_semantic_validator import (
    ModificationPlannerSemanticValidationError,
    validate_modification_plan_semantics,
)


plan_adapter = TypeAdapter(AiModificationPlan)


def make_context_payload() -> dict:
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
                    {
                        "id": "property-created-time",
                        "name": "Created time",
                        "type": "CREATED_TIME",
                        "position": "4",
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


def make_ready_plan_payload() -> dict:
    return {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "PLAN_READY",
        "summary": "Add a release task and checklist item.",
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


def parse_context(payload: dict | None = None) -> AiPageContext:
    return AiPageContext.model_validate(
        payload or make_context_payload(),
    )


def parse_plan(payload: dict | None = None) -> AiModificationPlan:
    return plan_adapter.validate_python(
        payload or make_ready_plan_payload(),
    )


def test_semantic_validator_accepts_valid_plan() -> None:
    context = parse_context()
    plan = parse_plan()

    result = validate_modification_plan_semantics(
        plan,
        context,
    )

    assert result is plan


def test_rejects_page_id_different_from_context() -> None:
    payload = make_ready_plan_payload()
    payload["pageId"] = "page-outside-context"

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="does not match context page",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_unknown_database() -> None:
    payload = make_ready_plan_payload()
    payload["operations"][0]["databaseId"] = "database-unknown"

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="Database database-unknown is not available",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_property_not_belonging_to_database() -> None:
    payload = make_ready_plan_payload()

    payload["operations"][0]["rows"][0]["values"] = {
        "property-outside-database": "Task",
    }

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="Property property-outside-database does not belong",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_option_from_another_property() -> None:
    payload = make_ready_plan_payload()

    payload["operations"][0]["rows"][0]["values"][
        "property-status"
    ] = "option-high"

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match=(
            "Option option-high does not belong to "
            "property property-status"
        ),
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_read_only_property_even_when_value_is_null() -> None:
    payload = make_ready_plan_payload()

    payload["operations"][0]["rows"][0]["values"] = {
        "property-created-time": None,
    }

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match=(
            "Property property-created-time of type "
            "CREATED_TIME is not writable"
        ),
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_value_not_matching_property_type() -> None:
    payload = make_ready_plan_payload()

    payload["operations"][0]["rows"][0]["values"][
        "property-points"
    ] = "three"

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="property-points.*finite number",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_unknown_parent_block() -> None:
    payload = make_ready_plan_payload()

    payload["operations"][1][
        "parentBlockId"
    ] = "block-unknown"

    payload["operations"][1]["afterBlockId"] = None

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="Parent block block-unknown is not available",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_parent_block_that_is_not_toggle() -> None:
    payload = make_ready_plan_payload()

    payload["operations"][1][
        "parentBlockId"
    ] = "block-header"

    payload["operations"][1]["afterBlockId"] = None

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="Parent block block-header cannot contain child blocks",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_anchor_from_different_sibling_group() -> None:
    payload = make_ready_plan_payload()

    payload["operations"][1][
        "parentBlockId"
    ] = "block-toggle"

    payload["operations"][1][
        "afterBlockId"
    ] = "block-header"

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="is not in the requested sibling group",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rejects_unknown_context_request_database() -> None:
    payload = {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "NEED_MORE_CONTEXT",
        "summary": "More row context is required.",
        "operations": [],
        "contextRequests": [
            {
                "reason": "AMBIGUOUS_TARGET",
                "description": "The target database is unclear.",
                "databaseId": "database-unknown",
            },
        ],
    }

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="database database-unknown is not available",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rows_truncated_reason_requires_truncated_rows() -> None:
    payload = {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "NEED_MORE_CONTEXT",
        "summary": "More rows are required.",
        "operations": [],
        "contextRequests": [
            {
                "reason": "ROWS_TRUNCATED",
                "description": "More rows are required.",
                "databaseId": "database-1",
            },
        ],
    }

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="rows are not marked as truncated",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_rows_truncated_reason_accepts_matching_completeness() -> None:
    context_payload = make_context_payload()

    context_payload["completeness"]["rows"][0][
        "truncated"
    ] = True

    context_payload["completeness"]["rows"][0][
        "total"
    ] = 100

    context_payload["completeness"]["rows"][0][
        "included"
    ] = 50

    payload = {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "NEED_MORE_CONTEXT",
        "summary": "More rows are required.",
        "operations": [],
        "contextRequests": [
            {
                "reason": "ROWS_TRUNCATED",
                "description": "The database row sample is incomplete.",
                "databaseId": "database-1",
            },
        ],
    }

    plan = parse_plan(payload)

    result = validate_modification_plan_semantics(
        plan,
        parse_context(context_payload),
    )

    assert result is plan


def test_text_truncated_reason_requires_matching_flag() -> None:
    payload = {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "NEED_MORE_CONTEXT",
        "summary": "More text is required.",
        "operations": [],
        "contextRequests": [
            {
                "reason": "TEXT_TRUNCATED",
                "description": "Some source text is incomplete.",
            },
        ],
    }

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="textTruncated=false",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_text_truncated_reason_accepts_matching_flag() -> None:
    context_payload = deepcopy(make_context_payload())

    context_payload["completeness"][
        "textTruncated"
    ] = True

    payload = {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "NEED_MORE_CONTEXT",
        "summary": "More text is required.",
        "operations": [],
        "contextRequests": [
            {
                "reason": "TEXT_TRUNCATED",
                "description": "Some source text is incomplete.",
            },
        ],
    }

    plan = parse_plan(payload)

    result = validate_modification_plan_semantics(
        plan,
        parse_context(context_payload),
    )

    assert result is plan 
def test_rejects_ambiguous_target_without_clarification_question() -> None:
    payload = {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "NEED_MORE_CONTEXT",
        "summary": "The target is ambiguous.",
        "operations": [],
        "contextRequests": [
            {
                "reason": "AMBIGUOUS_TARGET",
                "description": "More clarification is required.",
            },
        ],
    }

    with pytest.raises(
        ModificationPlannerSemanticValidationError,
        match="AMBIGUOUS_TARGET requires a clarification question",
    ):
        validate_modification_plan_semantics(
            parse_plan(payload),
            parse_context(),
        )


def test_accepts_ambiguous_target_with_clarification_question() -> None:
    payload = {
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": "page-1",
        "status": "NEED_MORE_CONTEXT",
        "summary": "The target is ambiguous.",
        "operations": [],
        "contextRequests": [
            {
                "reason": "AMBIGUOUS_TARGET",
                "description": "There are multiple possible targets.",
                "question": "Which target should be updated?",
            },
        ],
    }

    plan = parse_plan(payload)

    result = validate_modification_plan_semantics(
        plan,
        parse_context(),
    )

    assert result is plan