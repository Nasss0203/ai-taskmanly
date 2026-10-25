from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.shared.request_limits import CurrentPageId, Instruction, validate_input_budget


class PageIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: Instruction
    currentPageId: CurrentPageId | None = None

    @model_validator(mode="after")
    def validate_budget(self) -> "PageIntentRequest":
        validate_input_budget(self.instruction)
        return self


class PageIntentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Literal["MODIFY_PAGE", "OTHER", "UNCLEAR"]
    referenceType: Literal["TITLE", "CURRENT_PAGE", "UNRESOLVED"]
    pageReference: str | None
    instruction: str | None
    needsClarification: bool

    @model_validator(mode="after")
    def validate_combination(self) -> "PageIntentExtraction":
        if self.intent == "OTHER":
            if (
                self.referenceType != "UNRESOLVED"
                or self.pageReference is not None
                or self.instruction is not None
                or self.needsClarification
            ):
                raise ValueError("OTHER must not target a page or request clarification.")
            return self

        if self.intent == "UNCLEAR":
            if (
                self.referenceType != "UNRESOLVED"
                or self.pageReference is not None
                or self.instruction is not None
                or not self.needsClarification
            ):
                raise ValueError("UNCLEAR must require clarification without a target.")
            return self

        if self.instruction is None or not self.instruction.strip():
            raise ValueError("MODIFY_PAGE requires an editing instruction.")

        if self.referenceType == "TITLE":
            if (
                self.pageReference is None
                or not self.pageReference.strip()
                or self.needsClarification
            ):
                raise ValueError("TITLE requires a title and must not need clarification.")
        elif self.referenceType == "CURRENT_PAGE":
            if self.pageReference is not None or self.needsClarification:
                raise ValueError("CURRENT_PAGE must not have a title or need clarification.")
        else:
            if self.pageReference is not None or not self.needsClarification:
                raise ValueError("UNRESOLVED must have no title and require clarification.")
        return self


class PageIntentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: PageIntentExtraction
    provider: str
    model: str
