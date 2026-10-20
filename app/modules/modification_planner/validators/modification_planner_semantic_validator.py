from __future__ import annotations

import math
from typing import NoReturn

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiDateValue,
    AiModificationPlan,
    AiPageContext,
    AiPageContextBlock,
    AiPageContextDatabase,
    AiPageContextDatabaseProperty,
    CreateDatabaseRowsOperation,
    InsertBlocksOperation,
    ModificationContextRequest,
)


WRITABLE_PROPERTY_TYPES = frozenset(
    {
        "TITLE",
        "TEXT",
        "NUMBER",
        "SELECT",
        "STATUS",
        "MULTI_SELECT",
        "CHECKBOX",
        "DATE",
        "URL",
        "EMAIL",
        "PHONE",
    }
)

TEXT_PROPERTY_TYPES = frozenset(
    {
        "TITLE",
        "TEXT",
        "URL",
        "EMAIL",
        "PHONE",
    }
)


class ModificationPlannerSemanticValidationError(ValueError):
    pass


def validate_modification_plan_semantics(
    plan: AiModificationPlan,
    context: AiPageContext,
) -> AiModificationPlan:
    """
    Validate model output against the exact AiPageContext that was
    provided for the same planning request.

    This validator must not mutate the plan or context.
    """

    if plan.pageId != context.page.id:
        _fail(
            "Plan pageId "
            f"{plan.pageId} does not match context page "
            f"{context.page.id}",
        )

    for operation in plan.operations:
        if isinstance(operation, CreateDatabaseRowsOperation):
            _validate_create_database_rows(
                operation,
                context,
            )
            continue

        if isinstance(operation, InsertBlocksOperation):
            _validate_insert_blocks(
                operation,
                context,
            )
            continue

        _fail(
            "Unsupported modification operation returned "
            "after schema validation",
        )

    if plan.status == "NEED_MORE_CONTEXT":
        for request in plan.contextRequests:
            _validate_context_request(
                request,
                context,
            )

    return plan


def _validate_create_database_rows(
    operation: CreateDatabaseRowsOperation,
    context: AiPageContext,
) -> None:
    database = _find_database(
        context,
        operation.databaseId,
    )

    if database is None:
        _fail(
            f"Database {operation.databaseId} is not available "
            "in the current page context",
        )

    for row_index, row in enumerate(operation.rows):
        for property_id, value in row.values.items():
            property_ = _find_property(
                database,
                property_id,
            )

            if property_ is None:
                _fail(
                    f"Property {property_id} does not belong to "
                    f"database {database.id}",
                )

            _validate_property_value(
                property_,
                value,
                path=(
                    f"CREATE_DATABASE_ROWS.rows[{row_index}]"
                    f".values.{property_id}"
                ),
            )


def _validate_property_value(
    property_: AiPageContextDatabaseProperty,
    value: object,
    *,
    path: str,
) -> None:
    property_type = property_.type

    # Important:
    # Reject unsupported/system properties before handling null.
    if property_type not in WRITABLE_PROPERTY_TYPES:
        _fail(
            f"Property {property_.id} of type "
            f"{property_type} is not writable by "
            "Modification Planner v1",
        )

    if value is None:
        return

    if property_type in TEXT_PROPERTY_TYPES:
        if type(value) is not str:
            _fail(
                f"{path} must be a string or null",
            )

        return

    if property_type == "NUMBER":
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
        ):
            _fail(
                f"{path} must be a finite number or null",
            )

        return

    if property_type in {"SELECT", "STATUS"}:
        if type(value) is not str:
            _fail(
                f"{path} must be an option ID or null",
            )

        _validate_option_id(
            property_,
            value,
        )
        return

    if property_type == "MULTI_SELECT":
        if not isinstance(value, list):
            _fail(
                f"{path} must be an array of option IDs or null",
            )

        for option_index, option_id in enumerate(value):
            if type(option_id) is not str:
                _fail(
                    f"{path}[{option_index}] "
                    "must be an option ID",
                )

            _validate_option_id(
                property_,
                option_id,
            )

        return

    if property_type == "CHECKBOX":
        if type(value) is not bool:
            _fail(
                f"{path} must be a boolean or null",
            )

        return

    if property_type == "DATE":
        if not isinstance(value, AiDateValue):
            _fail(
                f"{path} must be a date object or null",
            )

        return

    _fail(
        f"Unsupported writable property type: {property_type}",
    )


def _validate_option_id(
    property_: AiPageContextDatabaseProperty,
    option_id: str,
) -> None:
    option_exists = any(
        option.id == option_id
        for option in property_.options
    )

    if not option_exists:
        _fail(
            f"Option {option_id} does not belong to "
            f"property {property_.id}",
        )


def _validate_insert_blocks(
    operation: InsertBlocksOperation,
    context: AiPageContext,
) -> None:
    parent_block: AiPageContextBlock | None = None

    if operation.parentBlockId is not None:
        parent_block = _find_block(
            context,
            operation.parentBlockId,
        )

        if parent_block is None:
            _fail(
                f"Parent block {operation.parentBlockId} "
                "is not available in the current page context",
            )

        if parent_block.type != "TOGGLE":
            _fail(
                f"Parent block {operation.parentBlockId} "
                "cannot contain child blocks",
            )

    if operation.afterBlockId is None:
        return

    anchor = _find_block(
        context,
        operation.afterBlockId,
    )

    if anchor is None:
        _fail(
            f"After block {operation.afterBlockId} "
            "is not available in the current page context",
        )

    if anchor.parentBlockId != operation.parentBlockId:
        _fail(
            f"After block {operation.afterBlockId} "
            "is not in the requested sibling group",
        )


def _validate_context_request(
    request: ModificationContextRequest,
    context: AiPageContext,
) -> None:
    if request.databaseId is not None:
        if (
            _find_database(
                context,
                request.databaseId,
            )
            is None
        ):
            _fail(
                f"Context request database "
                f"{request.databaseId} is not available "
                "in the current page context",
            )

    if request.blockId is not None:
        if (
            _find_block(
                context,
                request.blockId,
            )
            is None
        ):
            _fail(
                f"Context request block "
                f"{request.blockId} is not available "
                "in the current page context",
            )

    if request.reason == "AMBIGUOUS_TARGET":
        if request.question is None:
            _fail(
                "AMBIGUOUS_TARGET requires a clarification question",
            )

        return

    if request.reason == "ROWS_TRUNCATED":
        _validate_rows_truncated_reason(
            request,
            context,
        )
        return

    if request.reason == "TEXT_TRUNCATED":
        if not context.completeness.textTruncated:
            _fail(
                "TEXT_TRUNCATED was requested but the "
                "current context reports textTruncated=false",
            )


def _validate_rows_truncated_reason(
    request: ModificationContextRequest,
    context: AiPageContext,
) -> None:
    if request.databaseId is not None:
        completeness = next(
            (
                item
                for item in context.completeness.rows
                if item.databaseId == request.databaseId
            ),
            None,
        )

        if completeness is None:
            _fail(
                "ROWS_TRUNCATED references database "
                f"{request.databaseId}, but row completeness "
                "metadata is unavailable",
            )

        if not completeness.truncated:
            _fail(
                "ROWS_TRUNCATED references database "
                f"{request.databaseId}, but its rows are "
                "not marked as truncated",
            )

        return

    has_truncated_rows = any(
        item.truncated
        for item in context.completeness.rows
    )

    if not has_truncated_rows:
        _fail(
            "ROWS_TRUNCATED was requested but no database "
            "rows are marked as truncated",
        )


def _find_database(
    context: AiPageContext,
    database_id: str,
) -> AiPageContextDatabase | None:
    return next(
        (
            database
            for database in context.databases
            if database.id == database_id
        ),
        None,
    )


def _find_property(
    database: AiPageContextDatabase,
    property_id: str,
) -> AiPageContextDatabaseProperty | None:
    return next(
        (
            property_
            for property_ in database.properties
            if property_.id == property_id
        ),
        None,
    )


def _find_block(
    context: AiPageContext,
    block_id: str,
) -> AiPageContextBlock | None:
    return next(
        (
            block
            for block in context.blocks
            if block.id == block_id
        ),
        None,
    )


def _fail(
    message: str,
) -> NoReturn:
    raise ModificationPlannerSemanticValidationError(
        message,
    )