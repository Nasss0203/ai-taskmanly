from app.core.config import Settings
from app.llm.base import EmbeddingProvider, LLMProvider
from app.llm.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.ollama_embedding import OllamaEmbeddingProvider


def create_gemini_provider(settings: Settings) -> GeminiProvider:
    return GeminiProvider(
        api_key=settings.gemini_api_key.get_secret_value(),
        model_name=settings.gemini_model,
        timeout_seconds=settings.gemini_timeout_seconds,
        base_url=settings.gemini_base_url,
        thinking_level=settings.gemini_thinking_level,
        thinking_tokens=settings.gemini_thinking_tokens,
        max_retries=settings.gemini_max_retries,
    )


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()

    if settings.llm_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model_name=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            idle_timeout_seconds=settings.ollama_idle_timeout_seconds,
            num_ctx=settings.ollama_num_ctx,
            num_gpu=settings.ollama_num_gpu,
        )

    raise ValueError(
        f"Unsupported LLM provider: {settings.llm_provider}"
    )


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.llm_provider == "fake":
        return FakeEmbeddingProvider()

    if settings.llm_provider == "ollama":
        return OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model_name=settings.ollama_embedding_model,
            timeout_seconds=settings.ollama_embedding_timeout_seconds,
            num_gpu=settings.ollama_embedding_num_gpu,
        )

    raise ValueError(
        f"Unsupported LLM provider: {settings.llm_provider}"
    )
