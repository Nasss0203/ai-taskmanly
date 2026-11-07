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

LEAD = ("nho ban", "phien ban", "ban oi", "ban co the", "ban hay", "ban", "lam on", "vui long", "giup toi",
        "giup minh", "hay", "pls", "please", "can you", "could you", "cho toi", "cho minh")
ACTIONS = ("tom tat", "viet lai", "viet tiep", "rut gon", "mo rong", "dich", "translate", "summarize", "shorten",
           "rewrite", "expand", "continue", "paraphrase", "improve")
FILLER = ("giup toi", "giup minh", "gium toi", "gium minh", "giup", "gium", "doan nay", "cau nay", "cai nay",
          "doan sau", "cau sau", "doan van nay", "this", "it", "lai", "nay")
LANGUAGES = ("tieng tay ban nha", "tieng anh", "tieng viet", "tieng nhat", "tieng han", "tieng phap", "tieng duc",
             "tieng trung", "english", "vietnamese", "japanese", "korean", "french", "german", "chinese", "spanish")
TAIL = ("duoc khong", "duoc ko", "nhe ban", "nhe", "nha", "please", "giup toi", "giup minh", "gium", "voi")
# Translating takes any phrase ("dịch sang tiếng Anh cảm ơn anh"); for the other
# actions the words after the verb are usually how to write ("viết lại cho hay
# hơn"), so only a real passage counts.
MIN_WORDS = {"dich": 2, "translate": 2}
MIN_PASSAGE_WORDS = 8


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
    if at < len(folded) and folded[at] in ("sang", "to", "into", "qua"):
        size = _starts(folded, at + 1, LANGUAGES)
        return size + 1 if size else 0
    return 0


def inline_writing_text(instruction: str) -> str | None:
    words = [word.strip("\"'“”‘’`") for word in instruction.split()]
    words = [word for word in words if word]
    folded = [_fold(word) for word in words]
    start = 0
    while size := _starts(folded, start, LEAD):
        start += size
    action = _starts(folded, start, ACTIONS)
    if not action:
        return None
    verb = " ".join(folded[start:start + action])
    start += action
    end = len(words)
    changed = True
    while changed:
        changed = False
        for size in (_starts(folded, start, FILLER), _language_at(folded, start)):
            if size:
                start, changed = start + size, True
                break
        else:
            for size in (_ends(folded, end, TAIL),):
                if size and end - size >= start:
                    end, changed = end - size, True
            for back in range(2, 6):
                if end - back > start and _language_at(folded, end - back) == back:
                    end, changed = end - back, True
                    break
    text = words[start:end]
    if len(text) < MIN_WORDS.get(verb, MIN_PASSAGE_WORDS):
        return None
    return " ".join(text).strip(" :,.") or None
