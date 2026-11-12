"""The text a writing request works on when it has no ":" or quotes (kế hoạch sửa tính
năng viết, V2).

"dịch sang tiếng Anh chúc mọi người cuối tuần vui vẻ", "dịch cảm ơn anh rất nhiều
sang tiếng Anh": after the polite words, the writing verb, filler ("đoạn này",
"giúp tôi") and the target language, the words left are the text — when there
are at least two. NestJS ``inlineWritingText`` reads sentences the same way
(shared cases ``evaluation/writing_source_cases.json``).
"""

import re
import unicodedata

from app.shared.vi_vocabulary import words

LEAD = tuple(words("lead", "lead_short", "let_me"))
ACTIONS = tuple(words("write_translate", "write_improve", "write_shorten", "write_expand", "write_summarize",
                      "write_continue"))
PASSAGE = tuple(words("write_passage"))
PASSAGE_HEAD = tuple(words("write_passage_head"))
PASSAGE_POINTER = tuple(words("write_passage_pointer", "write_selection"))
FILLER = tuple(words("help_after_verb", "write_help_after_verb", "write_passage", "inline_lead_filler")) + (
    "this", "it", "lai", "nay")
STYLE_WORDS = tuple(words("write_style_improve", "write_style_shorten", "write_style_expand"))
LANGUAGE_BEFORE = tuple(words("language_prep", "language_noun"))
LANGUAGES = ("tieng tay ban nha", "tieng anh", "tieng viet", "tieng nhat", "tieng han", "tieng phap", "tieng duc",
             "tieng trung", "english", "vietnamese", "japanese", "korean", "french", "german", "chinese", "spanish")
TAIL = tuple(words("tail", "trailing_with"))
# Translating takes any phrase ("dịch sang tiếng Anh cảm ơn anh"); for the other
# actions the words after the verb are usually how to write ("viết lại cho hay
# hơn"), so only a real passage counts.
COMMAND_WORDS = tuple(words("lead", "let_me", "help_after_verb", "write_help_after_verb", "tail", "write_passage",
                            "write_passage_head", "write_passage_pointer", "write_selection", "write_soft_tail",
                            "write_style_improve", "write_style_shorten", "write_style_expand")) + LANGUAGES
MIN_WORDS = {"dich": 2, "translate": 2}
MIN_PASSAGE_WORDS = 8
SHORT_PASSAGE_WORDS = 4


def _fold(word: str) -> str:
    text = unicodedata.normalize("NFD", word).casefold().replace("đ", "d")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^\w-]", "", text)


def _starts(folded: list[str], at: int, phrases: tuple[str, ...]) -> int:
    """Words of the longest phrase found at ``at`` (0 if none)."""
    for phrase in sorted(phrases, key=lambda p: -len(p.split())):
        words = phrase.split()
        if folded[at:at + len(words)] == words:
            return len(words)
    return 0


def _ends(folded: list[str], end: int, phrases: tuple[str, ...]) -> int:
    for phrase in sorted(phrases, key=lambda p: -len(p.split())):
        words = phrase.split()
        if end - len(words) >= 0 and folded[end - len(words):end] == words:
            return len(words)
    return 0


def _language_at(folded: list[str], at: int) -> int:
    """ "sang tiếng Anh", "to English", "into Vietnamese" at ``at``."""
    before = _starts(folded, at, LANGUAGE_BEFORE) if at < len(folded) else 0
    if before:
        size = _starts(folded, at + before, LANGUAGES)
        return size + before if size else 0
    return 0


def _style_at(folded: list[str], at: int) -> int:
    if at >= len(folded) or folded[at] != "cho":
        return 0
    size = _starts(folded, at + 1, STYLE_WORDS)
    if not size:
        return 0
    return size + 1 + (folded[at + size + 1:at + size + 2] == ["hon"])


def _trim(folded: list[str], start: int, end: int) -> tuple[int, int, bool]:
    styled, changed = False, True
    while changed:
        changed = False
        for size in (_starts(folded, start, FILLER), _language_at(folded, start), _style_at(folded, start)):
            if size:
                styled = styled or bool(_style_at(folded, start))
                start, changed = start + size, True
                break
        else:
            for size in (_ends(folded, end, TAIL),):
                if size and end - size >= start:
                    end, changed = end - size, True
            for back in range(2, 6):
                if end - back >= start and (_language_at(folded, end - back) == back or _style_at(folded, end - back) == back):
                    styled = styled or _style_at(folded, end - back) == back
                    end, changed = end - back, True
                    break
    return start, end, styled


def _points_at_passage(folded: list[str], start: int, end: int) -> bool:
    for index in range(min(end, len(folded))):
        head = _starts(folded, index, PASSAGE_HEAD)
        if head and _starts(folded, index + head, PASSAGE_POINTER) and index + head + 1 > start:
            return True
    return False


def _content_words(folded: list[str], start: int, end: int) -> int:
    part, count, index = folded[:end], 0, start
    while index < end:
        size = _language_at(part, index) or _starts(part, index, COMMAND_WORDS)
        count, index = (count, index + size) if size else (count + 1, index + 1)
    return count


def _passage(words: list[str], folded: list[str], start: int, end: int, verb: str, styled: bool) -> str | None:
    if any(_starts(folded, index, PASSAGE) for index in range(start, end)) or _points_at_passage(folded, start, end):
        return None
    if _content_words(folded, start, end) < MIN_WORDS.get(verb, MIN_PASSAGE_WORDS if styled else SHORT_PASSAGE_WORDS):
        return None
    return " ".join(words[start:end]).strip(" :,.") or None


def _text_before_command(words: list[str], folded: list[str], start: int) -> str | None:
    for index in range(len(words) - 1, start, -1):
        if not words[index - 1].endswith(","):
            continue
        action = _starts(folded, index, ACTIONS)
        if not action:
            continue
        rest_start, rest_end, _ = _trim(folded, index + action, len(words))
        if rest_start < rest_end:
            return None
        return _passage(words, folded, start, index, " ".join(folded[index:index + action]), False)
    return None


def inline_writing_text(instruction: str) -> str | None:
    words = [word.strip("\"'“”‘’`") for word in instruction.split()]
    words = [word for word in words if word]
    folded = [_fold(word) for word in words]
    start = 0
    while size := _starts(folded, start, LEAD):
        start += size
    action = _starts(folded, start, ACTIONS)
    if not action:
        return _text_before_command(words, folded, start)
    verb = " ".join(folded[start:start + action])
    start, end, styled = _trim(folded, start + action, len(words))
    return _passage(words, folded, start, end, verb, styled)
