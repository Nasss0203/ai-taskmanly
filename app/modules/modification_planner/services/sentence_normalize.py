"""Everyday wording into the forms the rules read (kế hoạch sửa lỗi người dùng giả lập, S2–S5).

"Bạn có thể sửa giúp tôi A thành B được không" is "sửa A thành B"; "xoá 2 việc A
với B" is "xoá A và B"; "sửa A -> B" is "sửa A thành B". Matching runs on the
folded text (no marks) while every kept word stays as the user wrote it. Quoted
parts are never touched. NestJS ``normalizeCommand`` reads sentences the same way;
both are checked against the shared ``evaluation/normalization_cases.json``.
"""

import re
from collections.abc import Callable

from app.modules.modification_planner.services.sentence_text import Folded, command_text

QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”|'[^']*'|‘[^’]*’|`[^`]*`")

EDIT_VERB = r"(?:chinh sua|thay doi|doi|sua|thay|cap nhat|change|update|edit|rename)"
DELETE_VERB = r"(?:xoa(?: bo)?|go(?: bo)?|delete|remove)"
TICK_VERB = r"(?:bo tich|bo danh dau|danh dau(?: (?:da )?(?:xong|hoan thanh))?|tich(?: (?:da )?xong)?|hoan thanh|check|uncheck|mark)"
# Kế hoạch sửa tính năng viết (V1): writing verbs, so "bạn có thể dịch giúp tôi
# đoạn này … được không" reads as "dịch đoạn này …" for intent.
WRITE_VERB = (r"(?:dich|tom tat|viet lai|viet tiep|rut gon|mo rong|viet dai ra|viet hay hon|translate|"
              r"summarize|rewrite|shorten|expand|continue|paraphrase|improve)")
VERB = rf"(?:them|chen|bo sung|ghi them|add|insert|{EDIT_VERB}|{DELETE_VERB}|{TICK_VERB}|{WRITE_VERB})"
KIND = r"(?:to-do|todo|to-dos|todos|heading|tieu de|checklist|doan van|doan|dong|trich dan|ghi chu|viec|task|tasks|muc)"

# S2: requests wrapped in polite words.
LEAD = re.compile(
    r"^(?:(?:nho ban|phien ban|ban oi|ban co the|ban giup (?:minh|toi)|ban hay|ban|lam on|vui long|"
    r"giup (?:minh|toi)|hay|pls|plz|please|can you|could you|would you)"
    r"\s*,?\s+)+"
)
# "mình cần / tôi muốn thêm …": only before a verb ("mình cần một trang" creates a Page).
WANT = re.compile(rf"^(?:minh|toi|em) (?:can|muon) (?={VERB}\b)")
LET_ME = re.compile(
    rf"^cho (?:toi|minh|em) (?=(?:{EDIT_VERB}|{DELETE_VERB}|{TICK_VERB}|them|ghi them|chen|bo sung|tao|lap)\b)"
)
GIVE_PAGE = re.compile(
    r"^cho (?:toi|minh|em) (?:mot (?:trang|page)(?: moi)?(?: (?:co ten|ten))?"
    r"|(?:trang|page) (?:moi(?: (?:co ten|ten))?|co ten|ten)) (?=\S)"
)
DONE_SHORT = re.compile(r"(?<=\bxong) r(?=[\s.!?]*$)")
# "cho mình cái checklist …" asks for a block: it reads "thêm checklist …".
GIVE_ME = re.compile(rf"^cho (?:minh|toi|em)(?: (?:cai|mot|them))? (?={KIND}\b)")
TAIL = re.compile(
    r"(?:[\s,]+(?:duoc khong|duoc ko|dc ko|dc khong|duoc chu|nhe ban|nhe|nha|giup (?:minh|toi)|"
    r"gium(?: (?:minh|toi))?|please|pls|plz|thanks))+[\s.!?]*$"
)
# "đi", "với", "nữa", "cảm ơn" also end content ("bữa trưa mang đi", "thiệp cảm ơn"):
# dropped only when the sentence adds nothing ("xoá cái X đi", "giúp mình với").
LOOSE_TAIL = re.compile(r"(?:[\s,]+(?:di|voi|nua|giup|cam on))+[\s.!?]*$")
TARGET_BEFORE_TAIL = re.compile(
    r"\b(?:vao|o|trong|tai|tren|cua|cho|cuoi|dau)\s+(?:trang|page|bang|table)\s+[^,]+?"
    r"(?=(?:[\s,]+(?:di|voi|nua|giup|cam on))+[\s.!?]*$)"
)
INSERTS = re.compile(
    r"^(?:them|chen|bo sung|ghi them|add|insert|append|cho (?:minh|toi|em)|minh can|toi can|tao|lam|create|make)\b"
)
# P3 (kế hoạch sửa lỗi tạo trang): "làm cho mình cái trang …", "tạo giúp tôi một trang …".
CREATE_PAGE = re.compile(r"^(?:tao|lam)(?: (?:giup|gium|cho))?(?: (?:minh|toi|em))?(?: (?:mot|cai))* (?=(?:trang|page)\b)")
CREATE_START = re.compile(r"^(?:tao|create|make)(?: (?:mot|a|an|new))? (?:trang|page)\b")
# "xoá giúp mình …", "sửa giúp tôi …": the help words after the verb.
HELP_AFTER_VERB = re.compile(rf"^({VERB}) (?:giup|gium)(?: (?:minh|toi))?(?= |:|,)")
TICK_WORD = re.compile(r"(?:^|(?<=, ))(?:(?P<untick>untick|bo tick)|tick off|check off|tick)(?= )")
# "xoá cái A đi": "cái" names nothing.
THING_AFTER_VERB = re.compile(rf"^({DELETE_VERB}|{TICK_VERB}) cai ")
TO_DO = re.compile(r"\bto do\b")
ARROW = re.compile(r"\s*(?:->|→|=>)\s*")
VO = re.compile(r"\bvô\b|(?<!to-do )(?<!todo )(?<!viec )(?<!việc )(?<!them )(?<!thêm )\bvo\b(?= )", re.IGNORECASE)
COUNT = re.compile(rf"^({DELETE_VERB}|{TICK_VERB}) (?P<count>\d+) (?:viec|dong|to-do|todo|muc|cai|block|items?|tasks?) ")
WITH = re.compile(r" voi ")
EN_ITEM = re.compile(rf"^({DELETE_VERB}|{TICK_VERB}) the (?P<name>.+?) (?:item|task|to-do|todo)$")
# S3: the place before the verb; the unticked to-do named first.
# The Page named first moves to the end, where Page intent reads a target.
PLACE_FIRST = re.compile(
    r"^(?:(?P<page>(?:o|trong|tai|tren) (?:trang|page) [^,]+),\s*)?(?:(?:o|trong|tai) )?phan (?P<name>.+?),? "
    r"(?:(?:hay|ban) )*(?P<rest>them .+)$"
)
UNTICK_AFTER = re.compile(r"^(?:viec |to-do )?(?P<name>.+?),? chua xong,? (?:bo danh dau|bo tich)$")
# S5: "ghi thêm vào X: …", "ghi chú (lại): …", "thêm vào phần X: …".
WRITE_INTO = re.compile(r"^ghi them vao (?P<place>[^:]+?)\s*:\s*(?P<text>.+)$")
# Bước 4 (bỏ dấu hai chấm): "ghi chú dời họp sang thứ Năm" needs no ":".
NOTE = re.compile(r"^ghi chu(?: lai)?(?: (?:giup|gium)(?: (?:minh|toi))?)?(?:\s*:\s*|\s+)(?P<text>.+)$")
# P6: "thêm vào bảng Tasks dòng X (với trạng thái Done)" puts the table first.
TABLE_FIRST = re.compile(
    r"^them vao bang (?P<table>\S+(?: \S+)??) (?P<rest>(?:\d+ )?(?:dong|hang|tasks?|rows?|sach|cuon)\b.+)$"
)
PAGE_TAIL = re.compile(r"\s+(?:o|trong|tai|vao|cua|tren|on|in)\s+(?:the\s+)?(?:trang|page)\s+.+$")
ADD_INTO = re.compile(r"^them vao (?P<place>phan [^:]+?)\s*:\s*(?P<text>.+)$")


def _hide(text: str) -> tuple[str, list[str]]:
    found: list[str] = []

    def hide(match: re.Match[str]) -> str:
        found.append(match.group(0))
        return f"\x00{len(found) - 1}\x00"

    return QUOTED.sub(hide, text), found


def _show(text: str, quoted: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda match: quoted[int(match.group(1))], text)


def _sub(text: str, pattern: re.Pattern[str], build: Callable[[re.Match[str], Folded], str]) -> str:
    """Replace the first match found on the folded text; ``build`` gets the original words."""
    folded = Folded(text)
    match = pattern.search(folded.value)
    if match is None or match.end() == match.start():
        return text
    start, end = folded.span(*match.span())
    return text[:start] + build(match, folded) + text[end:]


def _group(match: re.Match[str], folded: Folded, name: str | int) -> str:
    return folded.original(*match.span(name)).strip()


def _names_count(rest: str) -> int:
    return len([part for part in re.split(r"\s*(?:,|\bva\b|\bvoi\b|\band\b)\s*", rest) if part.strip()])


def normalize_instruction(instruction: str) -> str:
    """The sentence in the forms the rules read; unchanged when nothing applies."""
    # Quotes first: their spacing and line breaks are content.
    text, quoted = _hide(instruction.strip())
    text = re.sub(r"\s+", " ", text)
    previous = None
    while previous != text:
        previous = text
        text = _sub(text, LEAD, lambda m, f: "")
        # "chủ nhà" folds to "nha" too: a tail holding "nhà" is content.
        tail = TAIL.search(Folded(text).value)
        if tail and "nhà" not in Folded(text).original(*tail.span()).casefold():
            text = _sub(text, TAIL, lambda m, f: "")
        if not INSERTS.match(Folded(text).value) or TARGET_BEFORE_TAIL.search(Folded(text).value):
            text = _sub(text, LOOSE_TAIL, lambda m, f: "")
    text = _sub(text, WANT, lambda m, f: "")
    text = _sub(text, LET_ME, lambda m, f: "")
    text = _sub(text, GIVE_PAGE, lambda m, f: "tạo trang ")
    text = _sub(text, DONE_SHORT, lambda m, f: " rồi")
    text = _sub(text, TICK_WORD, lambda m, f: "bỏ tích" if m.group("untick") else "tích")
    text = _sub(text, GIVE_ME, lambda m, f: "thêm ")
    # Only "làm …" or help words change; a plain "Tạo trang" keeps its own words.
    text = _sub(text, CREATE_PAGE, lambda m, f: "tạo " if m.group(0) != "tao " else f.original(*m.span()))
    text = _sub(text, HELP_AFTER_VERB, lambda m, f: _group(m, f, 1))
    text = _sub(text, THING_AFTER_VERB, lambda m, f: _group(m, f, 1) + " ")
    while TO_DO.search(Folded(text).value):
        text = _sub(text, TO_DO, lambda m, f: "to-do")
    text = VO.sub("vào", text)
    if re.match(rf"^{EDIT_VERB} ", Folded(text).value):
        text = ARROW.sub(" thành ", text)

    folded = Folded(text).value
    count = COUNT.match(folded)
    # "xoá 2 việc A với B": the number must be the number of names (else asked back).
    if count and int(count.group("count")) == _names_count(folded[count.end():]):
        text = _sub(text, COUNT, lambda m, f: _group(m, f, 1) + " ")
    if re.match(rf"^(?:{DELETE_VERB}|{TICK_VERB}) ", Folded(text).value):
        while WITH.search(Folded(text).value):
            text = _sub(text, WITH, lambda m, f: " và ")
        text = _sub(text, EN_ITEM, lambda m, f: f"{_group(m, f, 1)} {_group(m, f, 'name')}")

    text = _sub(text, PLACE_FIRST, lambda m, f: " ".join(filter(None, (
        _group(m, f, "rest"), "vào phần", _group(m, f, "name"),
        _group(m, f, "page") if m.group("page") else ""))))
    text = _sub(text, HELP_AFTER_VERB, lambda m, f: _group(m, f, 1))
    text = _sub(text, UNTICK_AFTER, lambda m, f: f"bỏ tích {_group(m, f, 'name')}")
    text = _sub(text, WRITE_INTO, lambda m, f: f'thêm đoạn văn "{_group(m, f, "text")}" vào {_group(m, f, "place")}')
    text = _sub(text, NOTE, lambda m, f: f'thêm ghi chú "{_group(m, f, "text")}"')
    text = _sub(text, TABLE_FIRST, lambda m, f: _table_first(_group(m, f, "table"), _group(m, f, "rest")))
    text = _sub(text, ADD_INTO,lambda m, f: _add_into(_group(m, f, "place"), _group(m, f, "text")))
    return _show(text.strip(), quoted)


def _table_first(table: str, rest: str) -> str:
    """ "2 dòng: A, B" stays a listed form; "dòng X …" moves before the table.

    A Page named at the end ("… ở trang Thử bảng AI 2") stays at the end, where
    Page intent reads it (live: it became "Thử bảng AI 2 vào bảng Tasks")."""
    folded = Folded(rest)
    target = PAGE_TAIL.search(folded.value)
    page = ""
    if target:
        page = " " + folded.original(target.start(), len(folded.value)).strip()
        rest = folded.original(0, target.start()).strip()
    if ":" in rest:
        kind, items = rest.split(":", 1)
        return f"thêm {kind.strip()} vào bảng {table}: {items.strip()}{page}"
    return f"thêm {rest} vào bảng {table}{page}"


def _add_into(place: str, text: str) -> str:
    """DS1: listed items (with a comma) are to-dos; one phrase is a paragraph."""
    if "," in text:
        return f"thêm checklist gồm {text} vào {place}"
    return f'thêm đoạn văn "{text}" vào {place}'


EDIT_START = re.compile(rf"^{VERB}\b")


def normalize_edit_instruction(instruction: str) -> str:
    """For intent: the normalized sentence only when it is an edit of a Page.

    "Giúp tôi lên kế hoạch …" (create) and "English please" (translate) keep their
    words, since the intent model reads the whole request.
    """
    normalized = normalize_instruction(instruction)
    folded = Folded(normalized).value
    command = Folded(command_text(normalized)).value
    return normalized if EDIT_START.match(folded) or EDIT_START.match(command) or CREATE_START.match(folded) else instruction


def normalize_create_instruction(instruction: str) -> str:
    """For page composition: the normalized sentence only when it creates a Page (P3)."""
    normalized = normalize_instruction(instruction)
    return normalized if CREATE_START.match(Folded(normalized).value) else instruction
