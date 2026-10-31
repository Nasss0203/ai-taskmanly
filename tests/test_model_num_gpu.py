"""OLLAMA_MODEL_NUM_GPU: one GPU placement per model, whatever the job."""

from fastapi.testclient import TestClient

from app.main import app


def start(monkeypatch, **environment):
    defaults = {
        "APP_ENV": "test",
        "AI_INTERNAL_TOKEN": "test-internal-service-token",
        "LLM_PROVIDER": "ollama",
        "OLLAMA_MODEL": "qwen3:1.7b",
        "OLLAMA_CONTINUE_MODEL": "qwen3:4b-instruct",
        "OLLAMA_PAGE_COMPOSITION_MODEL": "qwen3:4b-instruct",
        "OLLAMA_MODIFICATION_PLANNER_MODEL": "qwen3:4b-instruct",
        "OLLAMA_MODIFICATION_PLANNER_NUM_GPU": "8",
    }
    for name, value in {**defaults, **environment}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("OLLAMA_NUM_GPU", raising=False)
    return TestClient(app)


def test_each_model_gets_one_placement_for_every_job(monkeypatch) -> None:
    with start(monkeypatch, OLLAMA_MODEL_NUM_GPU='{"qwen3:1.7b": 0, "qwen3:4b-instruct": 99}') as client:
        state = client.app.state
        planner = state.modification_planner_service.llm_provider
        assert (planner.model_name, planner._num_gpu) == ("qwen3:4b-instruct", 99)
        # Composition and writing continue share the planner's loaded copy.
        assert state.page_composition_service.llm_provider is planner
        assert state.writing_service.continue_llm_provider is planner
        intent = state.page_intent_service.llm_provider
        assert (intent.model_name, intent._num_gpu) == ("qwen3:1.7b", 0)


def test_without_it_the_old_settings_apply(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL_NUM_GPU", raising=False)
    with start(monkeypatch, OLLAMA_MODEL_NUM_GPU="{}") as client:
        state = client.app.state
        assert state.modification_planner_service.llm_provider._num_gpu == 8
        assert state.page_composition_service.llm_provider._num_gpu is None
        assert state.page_intent_service.llm_provider._num_gpu is None
