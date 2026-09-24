from threading import Lock

from app.infrastructure.llm.base import LLMProvider


_llm_provider: LLMProvider | None = None
_llm_provider_lock = Lock()


def get_llm_provider() -> LLMProvider:
    global _llm_provider

    if _llm_provider is None:
        with _llm_provider_lock:
            if _llm_provider is None:
                from app.infrastructure.llm.qwen import QwenProvider

                _llm_provider = QwenProvider()

    return _llm_provider
