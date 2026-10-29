from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class PageActivity(BaseModel):
    """How the user named the Page: by their own edits (M2). Words only, no dates."""

    model_config = ConfigDict(extra="forbid", strict=True)

    relative: Literal["LATEST", "TODAY", "YESTERDAY", "N_DAYS_AGO", "LAST_WEEK", "RECENT"]
    days: int | None = Field(ge=1, le=30)
    titleHint: str | None = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_days(self) -> "PageActivity":
        if (self.relative == "N_DAYS_AGO") != (self.days is not None):
            raise ValueError("Only N_DAYS_AGO carries a number of days.")
        return self


class ActivityPageIntent(BaseModel):
    """MODIFY_PAGE of a Page named by activity. Never produced by the model:
    only the deterministic rules return it, and NestJS always asks the user
    to confirm the Page it finds."""

    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Literal["MODIFY_PAGE"]
    referenceType: Literal["ACTIVITY"]
    pageReference: None
    instruction: str = Field(min_length=1)
    needsClarification: Literal[False]
    activity: PageActivity


class PageScopeModel(BaseModel):
    """Where the named Page is (M4): an ancestor Page's title, or a teamspace."""

    model_config = ConfigDict(extra="forbid", strict=True)

    parentTitle: str | None = Field(min_length=1, max_length=255)
    teamspaceName: str | None = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_place(self) -> "PageScopeModel":
        if self.parentTitle is None and self.teamspaceName is None:
            raise ValueError("A scope names an ancestor Page or a teamspace.")
        return self


class ScopedTitlePageIntent(BaseModel):
    """MODIFY_PAGE of a titled Page in a named place. Only the deterministic
    rules return it; NestJS narrows Pages with that title to the place."""

    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Literal["MODIFY_PAGE"]
    referenceType: Literal["TITLE"]
    pageReference: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    needsClarification: Literal[False]
    scope: PageScopeModel


class DescriptionPageIntent(BaseModel):
    """MODIFY_PAGE of a Page named by what it is for (M6). Only the
    deterministic rules return it; NestJS offers the closest Pages and the
    user always picks one."""

    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Literal["MODIFY_PAGE"]
    referenceType: Literal["DESCRIPTION"]
    pageReference: None
    instruction: str = Field(min_length=1)
    needsClarification: Literal[False]
    description: str = Field(min_length=1, max_length=255)


class PageIntentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ActivityPageIntent adds the "activity" key, ScopedTitlePageIntent the
    # "scope" key and DescriptionPageIntent the "description" key; every other
    # result keeps exactly the five keys of PageIntentExtraction (the model's
    # schema).
    result: (
        PageIntentExtraction
        | ActivityPageIntent
        | ScopedTitlePageIntent
        | DescriptionPageIntent
    )
    provider: str
    model: str
