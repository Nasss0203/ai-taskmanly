import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.base import LLMGenerationResult, LLMTokenUsage
from app.llm.factory import create_gemini_provider
from app.llm.providers.gemini import GeminiProvider
from app.main import app

KEY = "TEST_GEMINI_KEY_FIXTURE_80431"
TASK_VARIABLES = ("WRITING_LLM_PROVIDER", "CONTINUE_LLM_PROVIDER", "PAGE_COMPOSITION_LLM_PROVIDER",
                  "MODIFICATION_PLANNER_LLM_PROVIDER", "PAGE_QUESTION_LLM_PROVIDER")


def settings(**values) -> Settings:
    return Settings(_env_file=None, app_env="test", **values)


def test_defaults_keep_every_task_on_the_main_provider(monkeypatch) -> None:
    for name in (*TASK_VARIABLES, "GEMINI_API_KEY", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    config = settings()
    assert config.writing_llm_provider is None
    assert config.continue_llm_provider is None
    assert config.page_composition_llm_provider is None
    assert config.modification_planner_llm_provider is None
    assert config.page_question_llm_provider is None
    assert config.gemini_api_key.get_secret_value() == ""
    assert config.gemini_model == "gemini-3.5-flash-lite"
    assert config.gemini_thinking_level == "MINIMAL"


@pytest.mark.parametrize("variable", TASK_VARIABLES)
def test_a_gemini_task_needs_the_key(monkeypatch, variable) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv(variable, "gemini")
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        settings()
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    assert settings().gemini_api_key.get_secret_value() == KEY


def test_an_empty_thinking_level_sends_no_thinking_setting(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", "")
    assert settings().gemini_thinking_level is None


def test_unknown_task_provider_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_LLM_PROVIDER", "openai")
    with pytest.raises(ValidationError):
        settings()


def test_the_key_never_shows_in_repr_or_errors(monkeypatch) -> None:
    config = settings(gemini_api_key=KEY, writing_llm_provider="gemini")
    assert KEY not in repr(config)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, app_env="invalid", gemini_api_key=KEY)
    assert KEY not in str(error.value)
    assert KEY not in error.value.json()


def test_factory_builds_the_gemini_provider() -> None:
    provider = create_gemini_provider(settings(gemini_api_key=KEY, gemini_model="gemini-3.6-flash",
                                               gemini_timeout_seconds=30))
    assert isinstance(provider, GeminiProvider)
    assert (provider.provider_name, provider.model_name) == ("gemini", "gemini-3.6-flash")
    asyncio.run(provider.close())


def start(monkeypatch, tmp_path, **environment):
    defaults = {
        "APP_ENV": "test",
        "AI_INTERNAL_TOKEN": "test-internal-service-token",
        "LLM_PROVIDER": "ollama",
        "OLLAMA_MODEL": "qwen3:1.7b",
        "OLLAMA_CONTINUE_MODEL": "qwen3:4b-instruct",
        "OLLAMA_PAGE_COMPOSITION_MODEL": "qwen3:4b-instruct",
        "OLLAMA_MODIFICATION_PLANNER_MODEL": "qwen3:4b-instruct",
    }
    for name in (*TASK_VARIABLES, "GEMINI_API_KEY", "OLLAMA_INTENT_MODEL", "OLLAMA_WRITING_MODEL",
                 "OLLAMA_MODEL_NUM_GPU", "OLLAMA_NUM_GPU", "OLLAMA_MODIFICATION_PLANNER_NUM_GPU"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {**defaults, **environment}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)
    return TestClient(app)


def providers(state) -> dict[str, object]:
    return {
        "writing": state.writing_service.llm_provider,
        "continue": state.writing_service.continue_llm_provider,
        "composition": state.page_composition_service.llm_provider,
        "planner": state.modification_planner_service.llm_provider,
        "question": state.page_question_service.llm_provider,
        "intent": state.intent_service.llm_provider,
        "page_intent": state.page_intent_service.llm_provider,
    }


def test_without_task_settings_nothing_uses_gemini(monkeypatch, tmp_path) -> None:
    with start(monkeypatch, tmp_path) as client:
        chosen = providers(client.app.state)
        assert {provider.provider_name for provider in chosen.values()} == {"ollama"}
        assert chosen["question"] is chosen["writing"]


def test_only_the_named_task_moves_to_gemini(monkeypatch, tmp_path) -> None:
    with start(monkeypatch, tmp_path, WRITING_LLM_PROVIDER="gemini", GEMINI_API_KEY=KEY) as client:
        chosen = providers(client.app.state)
        assert isinstance(chosen["writing"], GeminiProvider)
        assert chosen["continue"].model_name == "qwen3:4b-instruct"
        assert chosen["continue"].provider_name == "ollama"
        for name in ("composition", "planner", "intent", "page_intent"):
            assert chosen[name].provider_name == "ollama"
        assert chosen["question"] is chosen["writing"]


def test_question_can_differ_from_writing(monkeypatch, tmp_path) -> None:
    with start(monkeypatch, tmp_path, WRITING_LLM_PROVIDER="gemini", PAGE_QUESTION_LLM_PROVIDER="ollama",
               GEMINI_API_KEY=KEY) as client:
        chosen = providers(client.app.state)
        assert isinstance(chosen["writing"], GeminiProvider)
        assert (chosen["question"].provider_name, chosen["question"].model_name) == ("ollama", "qwen3:1.7b")


def test_every_content_task_shares_one_gemini_provider(monkeypatch, tmp_path) -> None:
    environment = {name: "gemini" for name in TASK_VARIABLES}
    with start(monkeypatch, tmp_path, GEMINI_API_KEY=KEY, GEMINI_MODEL="gemini-3.6-flash", **environment) as client:
        chosen = providers(client.app.state)
        gemini = chosen["writing"]
        assert isinstance(gemini, GeminiProvider) and gemini.model_name == "gemini-3.6-flash"
        for name in ("continue", "composition", "planner", "question"):
            assert chosen[name] is gemini
        assert chosen["intent"].provider_name == "ollama"
        assert chosen["page_intent"].provider_name == "ollama"


def test_planner_alone_on_gemini(monkeypatch, tmp_path) -> None:
    with start(monkeypatch, tmp_path, MODIFICATION_PLANNER_LLM_PROVIDER="gemini", GEMINI_API_KEY=KEY) as client:
        chosen = providers(client.app.state)
        assert isinstance(chosen["planner"], GeminiProvider)
        assert chosen["composition"].provider_name == "ollama"


class Recording:
    provider_name = "gemini"
    model_name = "gemini-test"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, system_prompt, user_prompt, max_new_tokens=300, response_schema=None):
        self.calls += 1
        return LLMGenerationResult(text="ok", usage=LLMTokenUsage(prompt_tokens=7, completion_tokens=3,
                                                                  total_tokens=10))

    async def close(self) -> None:
        return None


def test_metered_provider_counts_calls_time_and_tokens() -> None:
    from scripts.evaluate_end_to_end import Metered

    clock = iter([0.0, 2.0, 2.0, 5.0])
    metered = Metered(Recording(), clock=lambda: next(clock))
    asyncio.run(metered.generate("s", "u"))
    asyncio.run(metered.generate("s", "u"))
    assert (metered.provider_name, metered.model_name) == ("gemini", "gemini-test")
    assert metered.report() == {"provider": "gemini", "model": "gemini-test", "calls": 2, "seconds": 5.0,
                                "promptTokens": 14, "completionTokens": 6}


def test_metered_provider_spaces_out_calls() -> None:
    from scripts.evaluate_end_to_end import Metered

    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    clock = iter([10.0, 10.0, 11.0, 11.5, 15.0, 16.0])
    metered = Metered(Recording(), interval=4.0, sleep=sleep, clock=lambda: next(clock))
    asyncio.run(metered.generate("s", "u"))
    asyncio.run(metered.generate("s", "u"))
    assert waits == [2.5]


@pytest.mark.parametrize(("provider", "used"), [
    ("ollama", True), ("gemini", True), ("deterministic", False), ("rules", False),
])
def test_used_model_counts_any_model_provider(provider, used) -> None:
    from scripts.evaluate_end_to_end import used_model

    assert used_model(provider) is used


def test_evaluation_services_follow_the_task_settings() -> None:
    from scripts.evaluate_end_to_end import build_services, close_services

    config = settings(gemini_api_key=KEY, modification_planner_llm_provider="gemini",
                      writing_llm_provider="gemini", ollama_model="qwen3:4b-instruct")
    services = build_services(config)
    try:
        assert services.planner.llm_provider.provider_name == "gemini"
        assert services.intents.llm_provider.provider_name == "ollama"
        assert services.pages.llm_provider.provider_name == "ollama"
        assert services.writer_provider.provider_name == "gemini"
        assert services.composer_provider.provider_name == "ollama"
        assert services.question_provider is services.writer_provider
        assert {"intent", "planner", "writing", "composition", "question"} <= set(services.meters)
    finally:
        asyncio.run(close_services(services))


def test_usage_report_names_the_tasks_of_each_provider() -> None:
    from types import SimpleNamespace

    from scripts.evaluate_end_to_end import Metered, meter_snapshot, meter_usage

    intent, writer = Metered(Recording()), Metered(Recording())
    services = SimpleNamespace(providers=[intent, writer],
                               meters={"intent": intent, "writing": writer, "question": writer})
    before = meter_snapshot(services)
    asyncio.run(writer.generate("s", "u"))
    used = meter_usage(services, before)
    assert [item["tasks"] for item in used] == [["writing", "question"]]
