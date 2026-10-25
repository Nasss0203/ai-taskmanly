from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.request_limits import CurrentPageId, Instruction, WritingText, validate_input_budget


IntentType = Literal['CREATE_PAGE', 'MODIFY_PAGE', 'WRITING', 'OTHER', 'UNCLEAR']
WritingActionName = Literal['IMPROVE', 'SHORTEN', 'EXPAND', 'SUMMARIZE', 'CONTINUE', 'TRANSLATE']
Language = Annotated[str, Field(min_length=1, max_length=100)]


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    instruction: Instruction
    selectedText: WritingText | None = None
    currentPageId: CurrentPageId | None = None

    @model_validator(mode='after')
    def validate_budget(self) -> 'IntentRequest':
        validate_input_budget(self.model_dump(exclude_none=True))
        return self


class IntentExtraction(BaseModel):
    """Strict LLM boundary: no IDs, title, editing instruction or execution."""
    model_config = ConfigDict(extra='forbid', strict=True)

    intent: IntentType
    writingAction: WritingActionName | None
    language: Language | None

    @model_validator(mode='after')
    def validate_combination(self) -> 'IntentExtraction':
        if self.intent == 'WRITING':
            if self.writingAction is None:
                raise ValueError('WRITING requires a supported action.')
            if self.writingAction != 'TRANSLATE' and self.language is not None:
                raise ValueError('Only TRANSLATE may specify language.')
        elif self.writingAction is not None or self.language is not None:
            raise ValueError('Non-Writing intent must not carry action or language.')
        if self.language is not None and not self.language.strip():
            raise ValueError('Language must not be blank.')
        return self


class IntentResult(IntentExtraction):
    writingAction: WritingActionName | None = None
    language: Language | None = None
    needsClarification: bool = False


class IntentResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    result: IntentResult
    provider: str
    model: str
