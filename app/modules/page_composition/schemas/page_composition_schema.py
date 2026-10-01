from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)


PAGE_COMPOSITION_SCHEMA_VERSION = 1
MAX_PAGE_COMPOSITION_ROWS = 20


class PageCompositionBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class PageCompositionRequest(PageCompositionBaseModel):
    instruction: str = Field(min_length=1)
    context: dict[str, Any] | None = None


class PageCompositionPage(PageCompositionBaseModel):
    title: str
    icon: str | None = None
    coverUrl: str | None = None


class PageCompositionTextContent(PageCompositionBaseModel):
    text: str


class PageCompositionTodoContent(PageCompositionBaseModel):
    text: str
    checked: StrictBool


class PageCompositionHeaderStyleConfig(PageCompositionBaseModel):
    level: StrictInt


class PageCompositionBlockBase(PageCompositionBaseModel):
    ref: str
    parentRef: str | None = None

    orderIndex: Annotated[
        StrictInt,
        Field(ge=0),
    ] | None = None


class PageCompositionTextBlock(PageCompositionBlockBase):
    type: Literal["TEXT"]
    content: PageCompositionTextContent


class PageCompositionHeaderBlock(PageCompositionBlockBase):
    type: Literal["HEADER"]
    content: PageCompositionTextContent
    styleConfig: PageCompositionHeaderStyleConfig | None = None


class PageCompositionQuoteBlock(PageCompositionBlockBase):
    type: Literal["QUOTE"]
    content: PageCompositionTextContent


class PageCompositionTodoBlock(PageCompositionBlockBase):
    type: Literal["TODO"]
    content: PageCompositionTodoContent


class PageCompositionToggleBlock(PageCompositionBlockBase):
    type: Literal["TOGGLE"]
    content: PageCompositionTextContent


class PageCompositionDatabaseViewBlock(PageCompositionBlockBase):
    type: Literal["DATABASE_VIEW"]
    databaseRef: str
    viewRef: str


PageCompositionBlock = Annotated[
    PageCompositionTextBlock
    | PageCompositionHeaderBlock
    | PageCompositionQuoteBlock
    | PageCompositionTodoBlock
    | PageCompositionToggleBlock
    | PageCompositionDatabaseViewBlock,
    Field(discriminator="type"),
]


class PageCompositionPropertyOption(PageCompositionBaseModel):
    ref: str
    name: str
    color: str | None = None


class PageCompositionProperty(PageCompositionBaseModel):
    ref: str
    name: str

    type: Literal[
        "TITLE",
        "TEXT",
        "NUMBER",
        "SELECT",
        "CHECKBOX",
        "DATE",
    ]

    options: list[PageCompositionPropertyOption] | None = None


class PageCompositionView(PageCompositionBaseModel):
    ref: str
    name: str
    type: Literal["TABLE"]


class PageCompositionDateValue(PageCompositionBaseModel):
    start: str
    end: str | None = None


class PageCompositionSelectValue(PageCompositionBaseModel):
    optionRef: str


PageCompositionRowValue = (
    StrictStr
    | StrictInt
    | StrictFloat
    | StrictBool
    | PageCompositionDateValue
    | PageCompositionSelectValue
    | None
)


class PageCompositionRow(PageCompositionBaseModel):
    ref: str | None = None
    values: dict[str, PageCompositionRowValue]


class PageCompositionDatabase(PageCompositionBaseModel):
    ref: str
    name: str

    properties: list[PageCompositionProperty]

    views: list[PageCompositionView]

    rows: Annotated[
        list[PageCompositionRow],
        Field(max_length=MAX_PAGE_COMPOSITION_ROWS),
    ]


class PageCompositionDraft(PageCompositionBaseModel):
    schemaVersion: Literal[1]
    type: Literal["PAGE_COMPOSITION"]

    page: PageCompositionPage

    blocks: list[PageCompositionBlock]

    databases: Annotated[
        list[PageCompositionDatabase],
        Field(max_length=1),
    ]


class PageCompositionUsage(PageCompositionBaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class PageCompositionResponse(PageCompositionBaseModel):
    result: PageCompositionDraft
    provider: str
    model: str
    usage: PageCompositionUsage | None = None