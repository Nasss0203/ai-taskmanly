from collections.abc import Iterable
from typing import Any

from app.modules.page_composition.schemas.page_composition_schema import (
    PageCompositionDateValue,
    PageCompositionDraft,
    PageCompositionSelectValue,
)


class PageCompositionSemanticValidationError(ValueError):
    pass


def validate_page_composition_semantics(
    draft: PageCompositionDraft,
) -> PageCompositionDraft:
    _validate_block_refs(draft)
    _validate_database_refs(draft)
    _validate_database_view_references(draft)
    _validate_row_references(draft)

    return draft


def _validate_block_refs(
    draft: PageCompositionDraft,
) -> None:
    _ensure_unique_refs(
        draft.blocks,
        "block",
    )


def _validate_database_refs(
    draft: PageCompositionDraft,
) -> None:
    _ensure_unique_refs(
        draft.databases,
        "database",
    )

    for database in draft.databases:
        _ensure_unique_refs(
            database.properties,
            f"property in database '{database.ref}'",
        )

        _ensure_unique_refs(
            database.views,
            f"view in database '{database.ref}'",
        )

        rows_with_refs = [
            row
            for row in database.rows
            if row.ref is not None
        ]

        _ensure_unique_refs(
            rows_with_refs,
            f"row in database '{database.ref}'",
        )

        for property_draft in database.properties:
            _validate_property_options(
                database_ref=database.ref,
                property_draft=property_draft,
            )


def _validate_property_options(
    database_ref: str,
    property_draft: Any,
) -> None:
    if property_draft.type == "SELECT":
        if not property_draft.options:
            raise PageCompositionSemanticValidationError(
                f"SELECT property '{property_draft.ref}' "
                f"in database '{database_ref}' "
                "must have at least one option."
            )

        _ensure_unique_refs(
            property_draft.options,
            (
                "SELECT option in property "
                f"'{property_draft.ref}'"
            ),
        )

        return

    if property_draft.options is not None:
        raise PageCompositionSemanticValidationError(
            f"Property '{property_draft.ref}' "
            f"of type '{property_draft.type}' "
            "must not define options."
        )


def _validate_database_view_references(
    draft: PageCompositionDraft,
) -> None:
    databases_by_ref = {
        database.ref: database
        for database in draft.databases
    }

    for block in draft.blocks:
        if block.type != "DATABASE_VIEW":
            continue

        database = databases_by_ref.get(
            block.databaseRef
        )

        if database is None:
            raise PageCompositionSemanticValidationError(
                "DATABASE_VIEW block "
                f"'{block.ref}' references unknown database "
                f"'{block.databaseRef}'."
            )

        view_refs = {
            view.ref
            for view in database.views
        }

        if block.viewRef not in view_refs:
            raise PageCompositionSemanticValidationError(
                "DATABASE_VIEW block "
                f"'{block.ref}' references unknown view "
                f"'{block.viewRef}' in database "
                f"'{database.ref}'."
            )


def _validate_row_references(
    draft: PageCompositionDraft,
) -> None:
    for database in draft.databases:
        properties_by_ref = {
            property_draft.ref: property_draft
            for property_draft in database.properties
        }

        for row_index, row in enumerate(
            database.rows,
            start=1,
        ):
            for property_ref, value in row.values.items():
                property_draft = properties_by_ref.get(
                    property_ref
                )

                if property_draft is None:
                    raise PageCompositionSemanticValidationError(
                        f"Row {row_index} in database "
                        f"'{database.ref}' references unknown property "
                        f"'{property_ref}'."
                    )

                _validate_row_value_type(
                    database_ref=database.ref,
                    row_index=row_index,
                    property_draft=property_draft,
                    value=value,
                )

                if (
                    property_draft.type == "SELECT"
                    and value is not None
                ):
                    _validate_select_value(
                        database_ref=database.ref,
                        row_index=row_index,
                        property_draft=property_draft,
                        value=value,
                    )


def _validate_row_value_type(
    database_ref: str,
    row_index: int,
    property_draft: Any,
    value: Any,
) -> None:
    if value is None:
        return

    property_type = property_draft.type

    if property_type in ("TITLE", "TEXT"):
        if not isinstance(value, str):
            _raise_invalid_value_type(
                database_ref=database_ref,
                row_index=row_index,
                property_ref=property_draft.ref,
                property_type=property_type,
                value=value,
            )
        return

    if property_type == "NUMBER":
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
        ):
            _raise_invalid_value_type(
                database_ref=database_ref,
                row_index=row_index,
                property_ref=property_draft.ref,
                property_type=property_type,
                value=value,
            )
        return

    if property_type == "CHECKBOX":
        if not isinstance(value, bool):
            _raise_invalid_value_type(
                database_ref=database_ref,
                row_index=row_index,
                property_ref=property_draft.ref,
                property_type=property_type,
                value=value,
            )
        return

    if property_type == "DATE":
        if not isinstance(
            value,
            PageCompositionDateValue,
        ):
            _raise_invalid_value_type(
                database_ref=database_ref,
                row_index=row_index,
                property_ref=property_draft.ref,
                property_type=property_type,
                value=value,
            )
        return

    if property_type == "SELECT":
        if not isinstance(
            value,
            PageCompositionSelectValue,
        ):
            _raise_invalid_value_type(
                database_ref=database_ref,
                row_index=row_index,
                property_ref=property_draft.ref,
                property_type=property_type,
                value=value,
            )
        return

    raise PageCompositionSemanticValidationError(
        f"Unsupported property type '{property_type}' "
        f"for property '{property_draft.ref}'."
    )


def _validate_select_value(
    database_ref: str,
    row_index: int,
    property_draft: Any,
    value: Any,
) -> None:
    if not isinstance(
        value,
        PageCompositionSelectValue,
    ):
        raise PageCompositionSemanticValidationError(
            f"Row {row_index} in database "
            f"'{database_ref}' has invalid SELECT value for "
            f"property '{property_draft.ref}'."
        )

    valid_option_refs = {
        option.ref
        for option in property_draft.options
    }

    if value.optionRef not in valid_option_refs:
        raise PageCompositionSemanticValidationError(
            f"Row {row_index} in database "
            f"'{database_ref}' references unknown SELECT option "
            f"'{value.optionRef}' for property "
            f"'{property_draft.ref}'."
        )


def _raise_invalid_value_type(
    database_ref: str,
    row_index: int,
    property_ref: str,
    property_type: str,
    value: Any,
) -> None:
    raise PageCompositionSemanticValidationError(
        f"Row {row_index} in database "
        f"'{database_ref}' has invalid value type for property "
        f"'{property_ref}' of type '{property_type}': "
        f"received '{type(value).__name__}'."
    )


def _ensure_unique_refs(
    items: Iterable[Any],
    label: str,
) -> None:
    seen: set[str] = set()

    for item in items:
        ref = item.ref.strip()

        if ref in seen:
            raise PageCompositionSemanticValidationError(
                f"Duplicate {label} ref '{ref}'."
            )

        seen.add(ref)