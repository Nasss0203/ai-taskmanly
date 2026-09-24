from typing import Any

from pydantic import BaseModel

from app.modules.assistant.intent import AssistantIntent
from app.modules.assistant.schemas.context_schema import CurrentContext

class AssistantRequest(BaseModel):
    message: str
    current_context: CurrentContext | None = None


class AssistantResponse(BaseModel):
    intent: AssistantIntent
    data: dict[str, Any]