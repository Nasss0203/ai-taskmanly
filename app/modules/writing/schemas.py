from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WritingAction(str, Enum):
    IMPROVE = "IMPROVE"
    SHORTEN = "SHORTEN"
    EXPAND = "EXPAND"
    SUMMARIZE = "SUMMARIZE"
    TRANSLATE = "TRANSLATE"
    CONTINUE = "CONTINUE"


class WritingRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: WritingAction
    text: str = Field(min_length=1)
    target_language: str | None = Field(
        default=None,
        alias="targetLanguage",
        max_length=100,
    )
    tone: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "WritingRequest":
        if self.action == WritingAction.TRANSLATE:
            if not self.target_language or not self.target_language.strip():
                raise ValueError("targetLanguage is required for TRANSLATE.")
        return self


class WritingResponse(BaseModel):
    text: str
