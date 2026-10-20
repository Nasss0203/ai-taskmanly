from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.providers.fake import FakeLLMProvider
from app.llm.providers.ollama import OllamaProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()

    if settings.llm_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model_name=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            num_ctx=settings.ollama_num_ctx,
            num_gpu=settings.ollama_num_gpu,
        )

    raise ValueError(
        f"Unsupported LLM provider: {settings.llm_provider}"
    )