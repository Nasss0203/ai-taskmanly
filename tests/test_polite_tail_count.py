import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import AiPageContext
from app.modules.page_question.facts import database_answer
from scripts.evaluate_page_question import CONTEXTS

MEETING = AiPageContext.model_validate(CONTEXTS["meeting"])


@pytest.mark.parametrize(("question", "count"), [  # D-41
    ("bảng Tasks có bao nhiêu dòng nha", 7),
    ("bảng Tasks có bao nhiêu dòng với", 7),
    ("bảng Tasks có bao nhiêu việc Done giúp mình", 4),
    ("bảng Tasks có bao nhiêu việc To do nha", 2),
    ("bảng Tasks có bao nhiêu việc Done với nhé", 4),
    ("bang tasks co bao nhieu viec done nha", 4),
])
def test_a_polite_tail_is_no_status(question, count) -> None:
    _, data = database_answer(MEETING, question, "Tasks")
    assert data["rowCount"] == count


def test_an_unknown_status_is_still_named() -> None:
    answer, data = database_answer(MEETING, "bảng Tasks có bao nhiêu việc Huỷ nha", "Tasks")
    assert data["rowCount"] is None and "huy" in answer.casefold()
