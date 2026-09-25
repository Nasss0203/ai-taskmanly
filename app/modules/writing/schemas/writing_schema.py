from enum import Enum

from pydantic import AliasChoices, BaseModel, Field, model_validator


class WritingAction(str, Enum):
    IMPROVE = "IMPROVE"
    SHORTEN = "SHORTEN"
    EXPAND = "EXPAND"
    SUMMARIZE = "SUMMARIZE"
    TRANSLATE = "TRANSLATE"
    CONTINUE = "CONTINUE"


class WritingRequest(BaseModel):
    action: WritingAction
    text: str = Field(min_length=1)
    language: str | None = Field(
        default=None,
        max_length=100,
        validation_alias=AliasChoices("language", "targetLanguage"),
    )

    @model_validator(mode="after")
    def validate_translation_language(self) -> "WritingRequest":
        if self.action is WritingAction.TRANSLATE:
            if not self.language or not self.language.strip():
                raise ValueError("language is required for TRANSLATE.")
        return self


class WritingResponse(BaseModel):
    result: str
    provider: str
    model: str