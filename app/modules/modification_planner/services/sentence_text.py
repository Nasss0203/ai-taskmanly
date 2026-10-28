"""Shared reading of rule-based edit sentences (tích to-do, sửa chữ block).

The sentence is folded like NestJS ``foldInstruction`` for matching, while
every match maps back to the user's original words for drafts and messages.
"""

import re
import unicodedata

from app.shared.list_markers import strip_list_marker

COMMAND_PREFIX = re.compile(r"^(?:(?:hay|vui long|giup toi|giup minh|ban hay|please)\s+)+")
POLITE_SUFFIX = re.compile(r"(?:[\s,.!]+(?:nhe|nha|di|giup toi|giup minh|please))*[\s,.!]*$")
# The Page target ends the sentence; it is resolved elsewhere, never content.
TARGET = re.compile(
    r"[\s,]+(?:(?:vao|trong|o|cua|tai|on|in|to)\s+(?:the\s+)?(?:trang|page)\b"
    # English: the last "on/in/to … page"; "change X to Y on Z page" keeps "to Y".
    r"|(?:on|in|to)\s+(?:the\s+)?(?:(?!\s(?:on|in|to)\s).)+?\bpage\s*[.!]*$)",
)
PAGE_WORD = re.compile(r"\b(?:trang|page)\b")
QUOTES = "\"'`“”‘’"


def fold(text: str) -> str:
    """Lower case without Vietnamese marks, like NestJS ``foldInstruction``."""
    text = unicodedata.normalize("NFD", text).casefold().replace("đ", "d")
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def text_key(text: str) -> str:
    """Comparable form of a block's text or a name typed by the user."""
    key = fold(strip_list_marker(unicodedata.normalize("NFC", text)))
    return " ".join(re.sub(r"[^\w]+", " ", key).split())


class Folded:
    """Folded text that remembers where each character came from."""

    def __init__(self, text: str) -> None:
        self.text = text
        folded: list[str] = []
        self.positions: list[int] = []
        for index, char in enumerate(text):
            for piece in fold(char):
                folded.append(piece)
                self.positions.append(index)
        self.value = "".join(folded)

    def original(self, start: int, end: int) -> str:
        if end <= start:
            return ""
        return self.text[self.positions[start]: self.positions[end - 1] + 1]

    def span(self, start: int, end: int) -> tuple[int, int]:
        """The original (start, end) of a folded range."""
        return self.positions[start], self.positions[end - 1] + 1


def command_text(instruction: str) -> str:
    """The instruction without polite words and the Page target."""
    text = Folded(unicodedata.normalize("NFC", instruction).strip())
    start = COMMAND_PREFIX.match(text.value)
    begin = start.end() if start else 0
    target = TARGET.search(text.value, begin)
    end = target.start() if target else len(text.value)
    command = Folded(text.original(begin, end))
    polite = POLITE_SUFFIX.search(command.value)
    return command.original(0, polite.start() if polite else len(command.value))
