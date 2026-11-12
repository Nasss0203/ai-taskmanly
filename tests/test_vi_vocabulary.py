import copy
import re
from pathlib import Path

import pytest

from app.shared.vi_vocabulary import VOCABULARY_FILE, load, pattern, same_vocabulary, words

NESTJS_COPY = (Path(__file__).resolve().parents[2] / "be-task-management" / "src" / "modules" / "ai_assistant"
               / "application" / "services" / "ai-vi-vocabulary.json")


def test_every_group_holds_distinct_words() -> None:
    data = load(VOCABULARY_FILE)
    groups = {name: value for name, value in data.items() if not name.startswith("_")}
    assert groups
    for name, value in groups.items():
        assert value and all(isinstance(word, str) and word.strip() for word in value), name
        assert len(value) == len(set(value)), name


def test_python_and_nestjs_files_are_the_same() -> None:
    if not NESTJS_COPY.exists():
        pytest.skip("be-task-management is not next to this repository")
    assert same_vocabulary(load(VOCABULARY_FILE), load(NESTJS_COPY))


def test_one_word_of_difference_is_found() -> None:
    data = load(VOCABULARY_FILE)
    changed = copy.deepcopy(data)
    changed["tail"].append("thêm một từ")
    assert same_vocabulary(data, copy.deepcopy(data))
    assert not same_vocabulary(data, changed)


def test_folded_pattern_reads_typed_and_unmarked_spellings() -> None:
    tail = re.compile(rf"^{pattern('tail')}$")
    assert tail.match("giup minh") and tail.match("gium") and tail.match("duoc khong")
    assert not tail.match("a")


def test_marked_pattern_keeps_marks_for_words_that_fold_into_content() -> None:
    tail = re.compile(rf"^{pattern('tail', 'tail_marked_only', marked=True)}$", re.IGNORECASE)
    assert tail.match("ạ") and tail.match("nhé") and tail.match("nhe")
    assert not tail.match("a") and not tail.match("nhà")


def test_longest_phrase_wins() -> None:
    assert re.match(pattern("verb_tick"), "danh dau da xong").group() == "danh dau da xong"
    assert re.match(pattern("lead"), "ban oi").group() == "ban oi"


def test_words_are_folded_unless_marked() -> None:
    assert "giup minh" in words("lead")
    assert "giúp mình" in words("lead", marked=True)
    assert "lap" in words("verb_create_page")
