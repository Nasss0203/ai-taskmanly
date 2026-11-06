"""OLLAMA_MODEL_NUM_GPU: one GPU placement per model, whatever the job."""

from fastapi.testclient import TestClient

from app.main import app


def start(monkeypatch, tmp_path, **environment):
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
    # Settings reads ".env" from the working directory and merges its dict
    # values with these variables; run where there is no .env at all.
    monkeypatch.chdir(tmp_path)
    return TestClient(app)


def test_each_model_gets_one_placement_for_every_job(monkeypatch, tmp_path) -> None:
    with start(monkeypatch, tmp_path, OLLAMA_MODEL_NUM_GPU='{"qwen3:1.7b": 0, "qwen3:4b-instruct": 99}') as client:
        state = client.app.state
        planner = state.modification_planner_service.llm_provider
        assert (planner.model_name, planner._num_gpu) == ("qwen3:4b-instruct", 99)
        # Composition and writing continue share the planner's loaded copy.
        assert state.page_composition_service.llm_provider is planner
        assert state.writing_service.continue_llm_provider is planner
        intent = state.page_intent_service.llm_provider
        assert (intent.model_name, intent._num_gpu) == ("qwen3:1.7b", 0)


def test_without_it_the_old_settings_apply(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OLLAMA_MODEL_NUM_GPU", raising=False)
    with start(monkeypatch, tmp_path) as client:
        state = client.app.state
        assert state.modification_planner_service.llm_provider._num_gpu == 8
        assert state.page_composition_service.llm_provider._num_gpu is None
        assert state.page_intent_service.llm_provider._num_gpu is None


def test_intent_model_serves_intent_and_page_intent(monkeypatch, tmp_path) -> None:
    # Kế hoạch tốc độ Ask (A.2): page-intent took ~71% of an Ask on the 1.7B CPU copy.
    with start(monkeypatch, tmp_path, OLLAMA_INTENT_MODEL="qwen3:4b-instruct",
               OLLAMA_MODEL_NUM_GPU='{"qwen3:1.7b": 0, "qwen3:4b-instruct": 99}') as client:
        state = client.app.state
        planner = state.modification_planner_service.llm_provider
        # The same loaded 4B copy as the planner: one model on the GPU.
        assert state.intent_service.llm_provider is planner
        assert state.page_intent_service.llm_provider is planner
        # Writing keeps OLLAMA_MODEL.
        assert state.writing_service.llm_provider.model_name == "qwen3:1.7b"


def test_without_intent_model_intent_keeps_the_default_model(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OLLAMA_INTENT_MODEL", raising=False)
    with start(monkeypatch, tmp_path) as client:
        state = client.app.state
        assert state.intent_service.llm_provider is state.writing_service.llm_provider
        assert state.page_intent_service.llm_provider.model_name == "qwen3:1.7b"
