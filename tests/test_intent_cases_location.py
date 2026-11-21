from pathlib import Path

from scripts.evaluate_intent import DEFAULT_CASES
from training.prepare_dataset import INTENT_CASES

REPO = Path(__file__).resolve().parents[1]
IN_REPO = REPO / "evaluation" / "intent_cases.jsonl"


def test_intent_cases_live_in_the_repository() -> None:
    assert IN_REPO.is_file()
    assert DEFAULT_CASES == IN_REPO
    assert INTENT_CASES == IN_REPO
