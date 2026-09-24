from app.infrastructure.llm.base import LLMProvider
from app.infrastructure.llm.registry import get_llm_provider
from app.modules.task.prompts.generate_task_prompt import (
    GENERATE_TASK_SYSTEM_PROMPT,
)
from app.modules.task.schemas.task_schema import TaskGenerationResponse
from app.shared.json_parser import parse_json_object


class GenerateTaskService:
    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
    ):
        self.llm_provider = llm_provider

    def generate(self, prompt: str) -> dict:
        response = self._get_llm_provider().generate(
            system_prompt=GENERATE_TASK_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_new_tokens=400,
        )

        data = parse_json_object(response)
        task = TaskGenerationResponse(**data)

        if hasattr(task, "model_dump"):
            return task.model_dump()

        return task.dict()

    def _get_llm_provider(self) -> LLMProvider:
        if self.llm_provider is not None:
            return self.llm_provider

        return get_llm_provider()


generate_task_service = GenerateTaskService()
