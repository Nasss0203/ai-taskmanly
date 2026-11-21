from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.shared.request_limits import (
    MAX_INSTRUCTION_LENGTH,
    MAX_PAGE_INPUT_BYTES,
    validate_page_context,
    validate_page_input_budget,
)


def _validate_non_blank(value: str) -> str:

    if not value.strip():

        raise ValueError("must not be blank")



    return value





def _validate_schema_version(value: object) -> object:

    if type(value) is not int or value != 1:

        raise ValueError("schemaVersion must be integer 1")



    return value





def _validate_finite_number(

    value: float,

) -> int | float:

    if not math.isfinite(value):

        raise ValueError("number must be finite")



    return value





NonBlankString = Annotated[

    StrictStr,

    Field(min_length=1),

    AfterValidator(_validate_non_blank),

]



SchemaVersion = Annotated[

    Literal[1],

    BeforeValidator(_validate_schema_version),

]



StrictNumber = Annotated[

    StrictInt | StrictFloat,

    AfterValidator(_validate_finite_number),

]





class ModificationPlannerBaseModel(BaseModel):

    model_config = ConfigDict(extra="forbid")





class AiPageContextPage(

    ModificationPlannerBaseModel,

):

    id: NonBlankString

    workspaceId: NonBlankString

    teamspaceId: NonBlankString | None

    parentPageId: NonBlankString | None

    title: StrictStr

    icon: StrictStr | None

    coverUrl: StrictStr | None

    updatedAt: NonBlankString





class AiPageContextBlock(

    ModificationPlannerBaseModel,

):

    id: NonBlankString

    parentBlockId: NonBlankString | None

    type: NonBlankString



    orderIndex: Annotated[

        StrictInt,

        Field(ge=0),

    ]



    title: StrictStr | None

    content: dict[str, Any] | list[Any] | None

    styleConfig: dict[str, Any] | None

    dataConfig: dict[str, Any] | list[Any] | None





class AiPageContextDatabaseReference(

    ModificationPlannerBaseModel,

):

    blockId: NonBlankString

    databaseId: NonBlankString

    viewId: NonBlankString





class AiPageContextPropertyOption(

    ModificationPlannerBaseModel,

):

    id: NonBlankString

    name: StrictStr

    color: StrictStr | None

    position: StrictStr





class AiPageContextDatabaseProperty(

    ModificationPlannerBaseModel,

):

    id: NonBlankString

    name: StrictStr

    type: NonBlankString

    position: StrictStr

    isDefault: StrictBool

    isHideable: StrictBool

    options: list[AiPageContextPropertyOption]





class AiPageContextViewProperty(

    ModificationPlannerBaseModel,

):

    propertyId: NonBlankString

    position: StrictStr

    visible: StrictBool

    width: StrictNumber | None





class AiPageContextDatabaseView(

    ModificationPlannerBaseModel,

):

    id: NonBlankString

    databaseId: NonBlankString

    name: StrictStr

    type: NonBlankString

    position: StrictStr

    properties: list[AiPageContextViewProperty]





class AiDateValue(

    ModificationPlannerBaseModel,

):

    start: NonBlankString

    end: StrictStr | None = None





AiRowValueData = (

    StrictStr

    | StrictNumber

    | StrictBool

    | list[StrictStr]

    | AiDateValue

    | None

)





class AiPageContextDatabaseRow(

    ModificationPlannerBaseModel,

):

    id: NonBlankString

    databaseId: NonBlankString

    values: dict[str, AiRowValueData]





class AiPageContextDatabase(

    ModificationPlannerBaseModel,

):

    id: NonBlankString

    pageId: NonBlankString

    name: StrictStr

    properties: list[AiPageContextDatabaseProperty]

    views: list[AiPageContextDatabaseView]

    rows: list[AiPageContextDatabaseRow]





class AiPageContextCollectionCompleteness(

    ModificationPlannerBaseModel,

):

    total: Annotated[

        StrictInt,

        Field(ge=0),

    ]



    included: Annotated[

        StrictInt,

        Field(ge=0),

    ]



    truncated: StrictBool





class AiPageContextRowCompleteness(

    AiPageContextCollectionCompleteness,

):

    databaseId: NonBlankString

    selection: Literal["BOUNDED"]





class AiPageContextCompleteness(

    ModificationPlannerBaseModel,

):

    blocks: AiPageContextCollectionCompleteness

    databases: AiPageContextCollectionCompleteness

    rows: list[AiPageContextRowCompleteness]

    textTruncated: StrictBool





class AiPageContext(

    ModificationPlannerBaseModel,

):

    schemaVersion: SchemaVersion

    builtAt: NonBlankString

    page: AiPageContextPage



    blocks: list[AiPageContextBlock]



    databaseReferences: list[

        AiPageContextDatabaseReference

    ]



    databases: list[AiPageContextDatabase]



    completeness: AiPageContextCompleteness





# M8 (kế hoạch ngữ cảnh RAG, I4): passages of other Pages, read only. No Page
# or block IDs: the model cannot aim an operation at a source Page.
MAX_REFERENCES = 8
MAX_REFERENCE_TEXT_LENGTH = 400
MAX_REFERENCES_BYTES = 3000
MAX_INPUT_BYTES_WITH_REFERENCES = MAX_PAGE_INPUT_BYTES + MAX_REFERENCES_BYTES


class ModificationPlannerReference(

    ModificationPlannerBaseModel,

):

    label: Annotated[StrictStr, Field(pattern=r"^S[1-8]$")]

    pageTitle: Annotated[StrictStr, Field(max_length=255)]

    text: Annotated[NonBlankString, Field(max_length=MAX_REFERENCE_TEXT_LENGTH)]

    # Only for a named source Page read whole: the heading the passage sits
    # under, or that the passage is a heading itself.
    section: Annotated[StrictStr, Field(min_length=1, max_length=255)] | None = None

    isHeading: StrictBool = False


class ModificationPlannerRequest(

    ModificationPlannerBaseModel,

):

    instruction: Annotated[NonBlankString, Field(max_length=MAX_INSTRUCTION_LENGTH)]

    context: Annotated[AiPageContext, BeforeValidator(validate_page_context)]

    references: Annotated[
        list[ModificationPlannerReference] | None,
        Field(max_length=MAX_REFERENCES),
    ] = None

    @model_validator(mode="after")
    def validate_budget(self) -> ModificationPlannerRequest:
        if not self.references:
            validate_page_input_budget(self.model_dump(mode="json"))
            return self
        labels = [reference.label for reference in self.references]
        if len(set(labels)) != len(labels):
            raise ValueError("Reference labels must be unique.")
        if sum(len(reference.text.encode("utf-8")) for reference in self.references) > MAX_REFERENCES_BYTES:
            raise ValueError("References exceed the 3000-byte UTF-8 budget.")
        # The Page's own context keeps its 8000-byte limit; references add room.
        encoded = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_INPUT_BYTES_WITH_REFERENCES:
            raise ValueError(
                f"Combined AI input exceeds the {MAX_INPUT_BYTES_WITH_REFERENCES}-byte UTF-8 budget.",
            )
        return self





class CreateDatabaseRowInput(

    ModificationPlannerBaseModel,

):

    values: dict[str, AiRowValueData]





class CreateDatabaseRowsOperation(

    ModificationPlannerBaseModel,

):

    type: Literal["CREATE_DATABASE_ROWS"]

    databaseId: NonBlankString



    rows: Annotated[

        list[CreateDatabaseRowInput],

        Field(min_length=1),

    ]





class TextBlockContent(

    ModificationPlannerBaseModel,

):

    text: NonBlankString





class TodoBlockContent(

    ModificationPlannerBaseModel,

):

    text: NonBlankString

    checked: StrictBool





class HeaderStyleConfig(

    ModificationPlannerBaseModel,

):

    level: StrictInt | None = None



    @field_validator(

        "level",

        mode="before",

    )

    @classmethod

    def reject_explicit_null_level(

        cls,

        value: object,

    ) -> object:

        if value is None:

            raise ValueError(

                "level must be omitted instead of null",

            )



        return value





class TextBlockInput(

    ModificationPlannerBaseModel,

):

    type: Literal["TEXT"]

    content: TextBlockContent





class QuoteBlockInput(

    ModificationPlannerBaseModel,

):

    type: Literal["QUOTE"]

    content: TextBlockContent





class ToggleBlockInput(

    ModificationPlannerBaseModel,

):

    type: Literal["TOGGLE"]

    content: TextBlockContent





class TodoBlockInput(

    ModificationPlannerBaseModel,

):

    type: Literal["TODO"]

    content: TodoBlockContent





class HeaderBlockInput(

    ModificationPlannerBaseModel,

):

    type: Literal["HEADER"]

    content: TextBlockContent

    styleConfig: HeaderStyleConfig | None = None



    @field_validator(

        "styleConfig",

        mode="before",

    )

    @classmethod

    def reject_explicit_null_style_config(

        cls,

        value: object,

    ) -> object:

        if value is None:

            raise ValueError(

                "styleConfig must be omitted instead of null",

            )



        return value





ModificationBlockInput = Annotated[

    TextBlockInput

    | QuoteBlockInput

    | ToggleBlockInput

    | TodoBlockInput

    | HeaderBlockInput,

    Field(discriminator="type"),

]





class InsertBlocksOperation(

    ModificationPlannerBaseModel,

):

    type: Literal["INSERT_BLOCKS"]



    parentBlockId: NonBlankString | None



    afterBlockId: NonBlankString | None



    blocks: Annotated[

        list[ModificationBlockInput],

        Field(min_length=1),

    ]





class DeleteBlockOperation(ModificationPlannerBaseModel):
    # Kế hoạch xoá block: one block and everything nested in it (soft delete).
    # text and childCount must match the page, so nothing unseen is deleted.
    type: Literal["DELETE_BLOCK"]
    blockId: NonBlankString
    text: NonBlankString
    childCount: Annotated[StrictInt, Field(ge=0)]


class SetBlockTextOperation(ModificationPlannerBaseModel):
    # Kế hoạch sửa chữ block: only content.text of one existing block changes.
    # oldText must equal the block's current text; newText replaces it.
    type: Literal["SET_BLOCK_TEXT"]
    blockId: NonBlankString
    oldText: NonBlankString
    newText: Annotated[NonBlankString, Field(max_length=2000)]


class SetTodoCheckedOperation(ModificationPlannerBaseModel):
    # Kế hoạch tích to-do: only the checkbox of an existing TODO changes.
    # text is shown in the draft and must equal the block's current text.
    type: Literal["SET_TODO_CHECKED"]
    blockId: NonBlankString
    text: NonBlankString
    checked: StrictBool


AiModificationOperation = Annotated[

    CreateDatabaseRowsOperation

    | InsertBlocksOperation

    | SetTodoCheckedOperation

    | SetBlockTextOperation

    | DeleteBlockOperation,

    Field(discriminator="type"),

]





class CreateDatabaseRowsOperationBatch(

    ModificationPlannerBaseModel,

):

    operations: Annotated[

        list[CreateDatabaseRowsOperation],

        Field(min_length=1),

    ]





class InsertBlocksOperationBatch(

    ModificationPlannerBaseModel,

):

    operations: Annotated[

        list[InsertBlocksOperation],

        Field(min_length=1),

    ]






class ChecklistInsertBlocksOperation(
    ModificationPlannerBaseModel,
):
    type: Literal["INSERT_BLOCKS"]

    parentBlockId: NonBlankString | None

    afterBlockId: NonBlankString | None

    blocks: Annotated[
        list[TodoBlockInput],
        Field(min_length=1),
    ]


# A checklist under a requested heading: HEADER and TODO only (no TOGGLE/TEXT).
ChecklistWithHeadingBlockInput = Annotated[
    HeaderBlockInput | TodoBlockInput,
    Field(discriminator="type"),
]


class ChecklistWithHeadingInsertBlocksOperation(ModificationPlannerBaseModel):
    type: Literal["INSERT_BLOCKS"]
    parentBlockId: NonBlankString | None
    afterBlockId: NonBlankString | None
    blocks: Annotated[list[ChecklistWithHeadingBlockInput], Field(min_length=1)]


class ChecklistWithHeadingInsertBlocksOperationBatch(ModificationPlannerBaseModel):
    operations: Annotated[list[ChecklistWithHeadingInsertBlocksOperation], Field(min_length=1)]


class ChecklistWithHeadingMixedModificationOperationBatch(ModificationPlannerBaseModel):
    createDatabaseRowsOperations: Annotated[list[CreateDatabaseRowsOperation], Field(min_length=1)]
    insertBlocksOperations: Annotated[list[ChecklistWithHeadingInsertBlocksOperation], Field(min_length=1)]


class ChecklistInsertBlocksOperationBatch(
    ModificationPlannerBaseModel,
):
    operations: Annotated[
        list[ChecklistInsertBlocksOperation],
        Field(min_length=1),
    ]


class MixedModificationOperationBatch(

    ModificationPlannerBaseModel,

):

    createDatabaseRowsOperations: Annotated[

        list[CreateDatabaseRowsOperation],

        Field(min_length=1),

    ]



    insertBlocksOperations: Annotated[

        list[InsertBlocksOperation],

        Field(min_length=1),

    ]






class ChecklistMixedModificationOperationBatch(
    ModificationPlannerBaseModel,
):
    createDatabaseRowsOperations: Annotated[
        list[CreateDatabaseRowsOperation],
        Field(min_length=1),
    ]

    insertBlocksOperations: Annotated[
        list[ChecklistInsertBlocksOperation],
        Field(min_length=1),
    ]


ModificationOperationType = Literal[

    "CREATE_DATABASE_ROWS",

    "INSERT_BLOCKS",

]





class ModificationPlannerRoute(

    ModificationPlannerBaseModel,

):

    status: Literal[

        "PLAN_READY",

        "NEED_MORE_CONTEXT",

    ]



    operationTypes: Annotated[

        list[ModificationOperationType],

        Field(max_length=2),

    ]



    @model_validator(mode="after")

    def validate_route(

        self,

    ) -> ModificationPlannerRoute:

        if len(set(self.operationTypes)) != len(

            self.operationTypes

        ):

            raise ValueError(

                "operationTypes must not contain duplicates"

            )



        if (

            self.status == "PLAN_READY"

            and not self.operationTypes

        ):

            raise ValueError(

                "PLAN_READY requires at least one operation type"

            )



        if (

            self.status == "NEED_MORE_CONTEXT"

            and self.operationTypes

        ):

            raise ValueError(

                "NEED_MORE_CONTEXT must not contain "

                "operation types"

            )



        return self





ModificationContextRequestReason = Literal[

    "ROWS_TRUNCATED",

    "TEXT_TRUNCATED",

    "AMBIGUOUS_TARGET",

    "MISSING_RESOURCE_CONTEXT",

]





class ModificationContextRequest(

    ModificationPlannerBaseModel,

):

    reason: ModificationContextRequestReason

    description: NonBlankString



    databaseId: NonBlankString | None = None

    blockId: NonBlankString | None = None

    question: NonBlankString | None = None



    @field_validator(

        "databaseId",

        "blockId",

        "question",

        mode="before",

    )

    @classmethod

    def reject_explicit_null_optional_fields(

        cls,

        value: object,

    ) -> object:

        if value is None:

            raise ValueError(

                "optional field must be omitted instead of null",

            )



        return value





class ModificationNeedMoreContextDetails(

    ModificationPlannerBaseModel,

):

    summary: NonBlankString



    contextRequests: Annotated[

        list[ModificationContextRequest],

        Field(min_length=1),

    ]





class ModificationPlanReady(

    ModificationPlannerBaseModel,

):

    schemaVersion: SchemaVersion

    type: Literal["AI_MODIFICATION_PLAN"]

    pageId: NonBlankString

    status: Literal["PLAN_READY"]

    summary: NonBlankString



    operations: Annotated[

        list[AiModificationOperation],

        Field(min_length=1),

    ]





class ModificationPlanNeedMoreContext(

    ModificationPlannerBaseModel,

):

    schemaVersion: SchemaVersion

    type: Literal["AI_MODIFICATION_PLAN"]

    pageId: NonBlankString

    status: Literal["NEED_MORE_CONTEXT"]

    summary: NonBlankString



    operations: Annotated[

        list[AiModificationOperation],

        Field(max_length=0),

    ]



    contextRequests: Annotated[

        list[ModificationContextRequest],

        Field(min_length=1),

    ]





AiModificationPlan = Annotated[

    ModificationPlanReady

    | ModificationPlanNeedMoreContext,

    Field(discriminator="status"),

]





class ModificationPlannerUsage(

    ModificationPlannerBaseModel,

):

    prompt_tokens: Annotated[

        StrictInt,

        Field(ge=0),

    ]



    completion_tokens: Annotated[

        StrictInt,

        Field(ge=0),

    ]



    total_tokens: Annotated[

        StrictInt,

        Field(ge=0),

    ]





class ModificationPlannerResponse(

    ModificationPlannerBaseModel,

):

    result: AiModificationPlan

    provider: NonBlankString

    model: NonBlankString

    usage: ModificationPlannerUsage | None = None
