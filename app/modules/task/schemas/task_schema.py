from typing import Literal

from pydantic import BaseModel


class GenerationRequest(BaseModel):
    prompt: str


class TaskGenerationResponse(BaseModel):
    title: str
    description: str
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"]
    estimate: int | None = None
    acceptance_criteria: list[str]
