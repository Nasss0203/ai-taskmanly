import json
from pathlib import Path

import pytest

from app.modules.intent.services.writing_source import inline_writing_text

CASES = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "writing_source_cases.json")
                   .read_text(encoding="utf-8"))["cases"]


# Kế hoạch sửa tính năng viết (V2); the same cases run in NestJS.
@pytest.mark.parametrize("case", CASES, ids=[case["input"] for case in CASES])
def test_inline_writing_text(case: dict) -> None:
    assert inline_writing_text(case["input"]) == case["text"]
