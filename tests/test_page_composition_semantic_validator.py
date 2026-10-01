from copy import deepcopy
from typing import Any

import pytest

from app.modules.page_composition.schemas.page_composition_schema import (
    PageCompositionDraft,
)
from app.modules.page_composition.validators import (
    PageCompositionSemanticValidationError,
    validate_page_composition_semantics,
)


def make_valid_draft_data() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "type": "PAGE_COMPOSITION",
        "page": {
            "title": "Sprint Tasks",
        },
        "blocks": [
            {
                "ref": "header_sprint_tasks",
                "type": "HEADER",
                "content": {
                    "text": "Sprint Tasks",
                },
                "styleConfig": {
                    "level": 1,
                },
            },
            {
                "ref": "database_view_tasks",
                "type": "DATABASE_VIEW",
                "databaseRef": "database_tasks",
                "viewRef": "view_all_tasks",
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
                ],
                "views": [
                    {
                        "ref": "view_all_tasks",
                        "name": "All Tasks",
                        "type": "TABLE",
                    },
                ],
                "rows": [
                    {
                        "ref": "row_1",
                        "values": {
                            "property_name": "Implement login",
                            "property_status": {
                                "optionRef": "option_todo",
                            },
                            "property_estimate": 5,
                            "property_completed": False,
                        },
                    },
                    {
                        "ref": "row_2",
                        "values": {
                            "property_name": "Fix navbar",
                            "property_status": {
                                "optionRef": "option_done",
                            },
                            "property_estimate": 2,
                            "property_completed": True,
                        },
                    },
                ],
            },
        ],
    }


def make_valid_draft() -> PageCompositionDraft:
    return PageCompositionDraft.model_validate(
        make_valid_draft_data()
    )


def test_semantic_validator_accepts_valid_draft() -> None:
    draft = make_valid_draft()

    result = validate_page_composition_semantics(
        draft
    )

    assert result is draft


def test_semantic_validator_rejects_duplicate_block_ref() -> None:
    data = make_valid_draft_data()

    duplicate_block = deepcopy(
        data["blocks"][1]
    )

    data["blocks"].append(
        duplicate_block
    )

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        )


def test_semantic_validator_rejects_unknown_database_ref() -> None:
    data = make_valid_draft_data()

    data["blocks"][1]["databaseRef"] = (
        "database_missing"
    )

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        )


def test_semantic_validator_rejects_unknown_view_ref() -> None:
    data = make_valid_draft_data()

    data["blocks"][1]["viewRef"] = (
        "view_missing"
    )

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        )


def test_semantic_validator_rejects_unknown_property_ref() -> None:
    data = make_valid_draft_data()

    data["databases"][0]["rows"][0]["values"][
        "property_missing"
    ] = "Invalid value"

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        )


def test_semantic_validator_rejects_unknown_select_option() -> None:
    data = make_valid_draft_data()

    data["databases"][0]["rows"][1]["values"][
        "property_status"
    ] = {
        "optionRef": "option_missing",
    }

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        )


def test_semantic_validator_rejects_duplicate_property_ref() -> None:
    data = make_valid_draft_data()

    duplicate_property = deepcopy(
        data["databases"][0]["properties"][0]
    )

    data["databases"][0]["properties"].append(
        duplicate_property
    )

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        )


def test_semantic_validator_rejects_duplicate_select_option_ref() -> None:
    data = make_valid_draft_data()

    status_property = (
        data["databases"][0]["properties"][1]
    )

    duplicate_option = deepcopy(
        status_property["options"][0]
    )

    status_property["options"].append(
        duplicate_option
    )

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        )


def test_semantic_validator_rejects_duplicate_view_ref() -> None:
    data = make_valid_draft_data()

    duplicate_view = deepcopy(
        data["databases"][0]["views"][0]
    )

    data["databases"][0]["views"].append(
        duplicate_view
    )

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        )


def test_semantic_validator_rejects_duplicate_row_ref() -> None:
    data = make_valid_draft_data()

    data["databases"][0]["rows"][1]["ref"] = (
        "row_1"
    )

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError
    ):
        validate_page_composition_semantics(
            draft
        ) 
@pytest.mark.parametrize(
    (
        "property_definition",
        "property_ref",
        "invalid_value",
    ),
    [
        (
            None,
            "property_name",
            123,
        ),
        (
            None,
            "property_status",
            False,
        ),
        (
            None,
            "property_estimate",
            "five",
        ),
        (
            None,
            "property_completed",
            {
                "optionRef": "option_todo",
            },
        ),
        (
            {
                "ref": "property_notes",
                "name": "Notes",
                "type": "TEXT",
            },
            "property_notes",
            123,
        ),
        (
            {
                "ref": "property_due",
                "name": "Due",
                "type": "DATE",
            },
            "property_due",
            "2026-10-05",
        ),
    ],
    ids=[
        "title-rejects-number",
        "select-rejects-boolean",
        "number-rejects-string",
        "checkbox-rejects-select-value",
        "text-rejects-number",
        "date-rejects-string",
    ],
)
def test_semantic_validator_rejects_value_not_matching_property_type(
    property_definition: dict | None,
    property_ref: str,
    invalid_value: Any,
) -> None:
    data = make_valid_draft_data()

    if property_definition is not None:
        data["databases"][0]["properties"].append(
            property_definition
        )

    data["databases"][0]["rows"][0]["values"][
        property_ref
    ] = invalid_value

    draft = PageCompositionDraft.model_validate(
        data
    )

    with pytest.raises(
        PageCompositionSemanticValidationError,
        match=property_ref,
    ):
        validate_page_composition_semantics(
            draft
        ) 
def test_semantic_validator_rejects_select_property_without_options() -> None:
    data = make_valid_draft_data()

    for property_draft in data["databases"][0]["properties"]:
        if property_draft["ref"] == "property_status":
            property_draft.pop("options", None)
            break

    draft = PageCompositionDraft.model_validate(data)

    with pytest.raises(
        PageCompositionSemanticValidationError,
        match="must have at least one option",
    ):
        validate_page_composition_semantics(draft)


def test_semantic_validator_rejects_select_property_with_empty_options() -> None:
    data = make_valid_draft_data()

    for property_draft in data["databases"][0]["properties"]:
        if property_draft["ref"] == "property_status":
            property_draft["options"] = []
            break

    draft = PageCompositionDraft.model_validate(data)

    with pytest.raises(
        PageCompositionSemanticValidationError,
        match="must have at least one option",
    ):
        validate_page_composition_semantics(draft)


def test_semantic_validator_rejects_options_on_non_select_property() -> None:
    data = make_valid_draft_data()

    for property_draft in data["databases"][0]["properties"]:
        if property_draft["ref"] == "property_estimate":
            property_draft["options"] = [
                {
                    "ref": "option_invalid",
                    "name": "Invalid",
                }
            ]
            break

    draft = PageCompositionDraft.model_validate(data)

    with pytest.raises(
        PageCompositionSemanticValidationError,
        match="must not define options",
    ):
        validate_page_composition_semantics(draft)