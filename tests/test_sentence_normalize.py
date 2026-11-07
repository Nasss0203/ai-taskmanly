import json
from pathlib import Path

import pytest

from app.modules.modification_planner.services.sentence_normalize import normalize_instruction

CASES = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "normalization_cases.json")
                   .read_text(encoding="utf-8"))["cases"]


# Kế hoạch sửa lỗi người dùng giả lập (S2–S5); the same cases run in NestJS.
@pytest.mark.parametrize("case", CASES, ids=[case["input"] for case in CASES])
def test_everyday_wording_is_normalized(case: dict) -> None:
    assert normalize_instruction(case["input"]) == case["output"]


def test_a_house_is_not_a_polite_tail() -> None:
    # "nhà" folds to "nha" like the polite tail; content words stay.
    sentence = "thêm checklist gồm Lắp máy in và Trả chìa khoá cho chủ nhà"
    assert normalize_instruction(sentence) == sentence
    assert normalize_instruction("thêm heading Kết luận nha") == "thêm heading Kết luận"
