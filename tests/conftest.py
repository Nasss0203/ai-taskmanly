"""Shared test fixtures."""

import pytest


@pytest.fixture
def model_path(monkeypatch):
    """Send a sentence the rules could draft (kế hoạch bỏ qua model, F1) through
    the model path anyway, to test what happens to a model's answer."""
    from app.modules.modification_planner.services import modification_planner_service

    monkeypatch.setattr(modification_planner_service, "plan_explicit_content", lambda *args: None)
