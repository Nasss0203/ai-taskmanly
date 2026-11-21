import logging
from dataclasses import replace
from typing import Any

from app.core.exceptions import InvalidLLMResponseError, LLMProviderError
from app.llm.base import LLMGenerationResult, LLMProvider


logger = logging.getLogger(__name__)


class FallbackLLMProvider:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider_name = primary.provider_name
        self.model_name = primary.model_name

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 300,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        arguments = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_new_tokens": max_new_tokens,
            "response_schema": response_schema,
        }
        try:
            return self._named(await self.primary.generate(**arguments), self.primary)
        except InvalidLLMResponseError:
            raise
        except LLMProviderError as exc:
            logger.warning(
                "llm_fallback task_provider=%s fallback=%s model=%s reason=%s",
                self.primary.provider_name, self.fallback.provider_name, self.fallback.model_name,
                type(exc).__name__,
            )
        return self._named(await self.fallback.generate(**arguments), self.fallback)

    @staticmethod
    def _named(generation: LLMGenerationResult, provider: LLMProvider) -> LLMGenerationResult:
        return replace(
            generation,
            provider_name=generation.provider_name or provider.provider_name,
            model_name=generation.model_name or provider.model_name,
        )

    async def close(self) -> None:
        return None
