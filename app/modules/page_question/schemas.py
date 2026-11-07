from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.modules.modification_planner.schemas.modification_planner_schema import AiPageContext
from app.shared.request_limits import Instruction, validate_page_context, validate_page_input_budget

QuestionKind = Literal["TODO_STATUS", "DATABASE_COUNT", "SUMMARY", "FREE"]


class PageQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Instruction
    questionKind: QuestionKind
    databaseReference: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    context: Annotated[AiPageContext, BeforeValidator(validate_page_context)]

    @model_validator(mode="after")
    def validate_budget(self) -> "PageQuestionRequest":
        validate_page_input_budget(self.model_dump(mode="json"))
        return self


class PageQuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    usedModel: bool
    facts: dict[str, Any]
    provider: str
    model: str
