import json
import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any

VOCABULARY_FILE = Path(__file__).with_name("vi_vocabulary.json")
MARKED_ONLY = "tail_marked_only"


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text).casefold().replace("đ", "d")
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def same_vocabulary(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def groups(data: dict[str, Any]) -> dict[str, Any]:
        return {name: value for name, value in data.items() if not name.startswith("_")}

    return groups(first) == groups(second)


@cache
def _data() -> dict[str, Any]:
    return load(VOCABULARY_FILE)


def words(*groups: str, marked: bool = False) -> list[str]:
    found: list[str] = []
    for group in groups:
        for word in _data()[group]:
            spellings = [unicodedata.normalize("NFC", word), fold(word)] if marked else [fold(word)]
            if group == MARKED_ONLY:
                spellings = spellings[:1] if marked else []
            found += [spelling for spelling in spellings if spelling not in found]
    return found


def pattern(*groups: str, marked: bool = False) -> str:
    ordered = sorted(words(*groups, marked=marked), key=lambda word: (-len(word), word))
    return "(?:" + "|".join(re.escape(word).replace(r"\ ", r"\s+") for word in ordered) + ")"
