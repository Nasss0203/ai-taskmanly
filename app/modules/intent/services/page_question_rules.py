import re
import unicodedata
from dataclasses import dataclass

from app.modules.modification_planner.services.sentence_text import Folded, command_text, fold
from app.shared.vi_vocabulary import pattern

QUOTES = "\"'`“”‘’"
LEAD = pattern("lead")
EDIT_START = re.compile(
    rf"^(?:{LEAD}\s+)*"
    r"(?:them|chen|bo sung|ghi them|tich|danh dau|bo tich|bo danh dau|sua|chinh sua|doi|thay|thay doi|"
    r"cap nhat|xoa|bo|go|tao|lap|dich|viet|mo rong|rut gon|add|insert|append|tick|check|uncheck|mark|"
    r"change|update|edit|replace|rename|delete|remove|create|make|translate|write|move|di chuyen|"
    r"chuyen|nhan ban|duplicate|share|chia se)\b"
)
FOLLOW_UP_EDIT = re.compile(
    rf"\b(?:thi|roi|va|sau do|then|and)\s+(?:{LEAD}\s+)?"
    r"(?:them|tich|danh dau|sua|doi|xoa|bo|go|tao|add|tick|mark|delete|remove|update|change)\b"
)
MARKER = re.compile(r"(?<!\w)(?P<kind>trang|page|bang|table|database|co so du lieu)(?!\w)")
CURRENT = re.compile(r"^(?:nay|hien tai|dang mo|this|current)\b")
NOT_A_NAME = re.compile(r"^(?:nao|la gi|la cai gi|gi|which|nay\s+la)\b")
HOW_TO = re.compile(
    rf"^(?:{pattern('lead', 'lead_ask')}\s+)*"
    r"(?:cach\s+\w+|lam sao|lam the nao|huong dan|how (?:do|can|should) (?:i|we|you)|how to)\b"
)
HISTORY = re.compile(
    r"\b(?:them gi|da them|vua them|thay doi gi|sua gi|da sua|vua sua|ai sua|what changed|what was added)\b"
)
NAME_END = re.compile(
    r"\s*(?:[?,.!;:]|\s(?:con|co|da|chua|giup|noi|gom|thi|la|bao|ai|khi|duoc|hien|dang|ve|"
    r"may|tom tat|has|have|is|are|does|do|so|with|about|contain|contains)\b|"
    rf"\s{pattern('tail', 'trailing_go', 'trailing_with')}\s*(?=[?,.!;:]|$)|"
    r"\s(?:o|trong|tai|cua|thuoc)\s+(?=(?:trang|page|bang|table)\b)|\s(?:in|on|of)\s+the\s|$)"
)
ENGLISH_NAME = re.compile(r"(?:\b(?:in|on|of)\s+(?:the\s+)?|\bthe\s+)(?P<name>.+?)\s+(?:page|table|database)\b")
TODO_WORDS = re.compile(
    r"\b(?:chua xong|chua lam|chua hoan thanh|chua tich|da xong|da lam xong|da hoan thanh|da tich|"
    r"con (?:lai )?(?:gi|nhung gi|viec gi|viec nao|muc nao|to-?do nao|bao nhieu)|con viec|"
    r"unfinished|not done|not finished|left to do|still open|done yet|completed)\b"
)
TODO_ASKED_WORDS = re.compile(
    r"\b(?:con sot|xong roi|lam duoc|con (?:bao|may) viec|con lai|xong het|dang do|con thieu viec|hoan thanh duoc)\b"
)
ASK_CUE = re.compile(
    r"\?|\b(?:nao|gi|may|bao nhieu|bao viec|liet ke|what|which|how many|list|show|any)\b|\b(?:chua|khong)$"
)
TODO_LIST_ASK = re.compile(rf"^(?:{LEAD}\s+)*(?:nhung|cac)\s+viec\s+(?:con lai|chua xong|da xong|chua lam)\b")
QUESTION_TAIL = re.compile(
    rf"(?:\s+(?:{pattern('tail', 'trailing_with', 'trailing_go')}|vay|the|nhi|a|ha|nhe|nha|ma|dau))+$|\s*\?+$"
)
SUMMARY_AFTER = re.compile(
    r"(?:,?\s*(?:no|trang nay)\s+)?(?:(?:dang|chu yeu|da|thi)\s+)*"
    r"(?:(?:noi|viet|ghi)(?:\s+(?:cai|nhung))?\s+gi|co(?:\s+nhung)?(?:\s+(?:y|noi dung|thong tin))?\s+gi|"
    r"noi dung chinh(?:\s+la\s+gi)?|la\s+ve\s+(?:cai\s+)?gi)"
)
SUMMARY_BEFORE = re.compile(r"\b(?:noi dung|diem|y) chinh (?:cua )?(?:trang|page)\b")
SUMMARY_ASK = re.compile(
    rf"^(?:(?:{LEAD}|cho (?:minh|toi|em))\s+)*(?:diem qua|doc qua|giai thich ngan(?: gon)?|(?:cai nhin |xem )?tong quan)"
    r"(?:\s+(?:ve|cua))?\s+(?:trang|page)\b"
)
ONE_TASK_ASKED = re.compile(r"^(?P<task>.+?)\s+(?:o|trong|tai)\s+(?:trang|page)\s+.+?\s+(?:da\s+)?xong\s+(?:het\s+)?chua$")
COMMA_EDIT = re.compile(rf",\s*(?:{LEAD}\s+)?(?:bo tich|tich|danh dau|xoa|sua|them|doi)\b")
ASKED_ITEM = re.compile(r"\b(?:viec|muc|to-?do) (?:nao|gi)\b|\bnhung (?:viec|gi)\b")
NAMED_TASK = re.compile(r"\b(?:việc|to-do|todo)\s+(?=\w)", re.IGNORECASE)
TASK_END = re.compile(r"\s+(?:ở|trong|tại|của)\s+trang\b|\s+trang\b|[,?.!]|$", re.IGNORECASE)
COUNT_WORDS = re.compile(
    r"\b(?:bao nhieu|how many|dem|may (?:viec|dong|hang|muc|tasks?|nguoi|cai|ban ghi|cong viec))\b"
)
SUMMARY_WORDS = re.compile(
    r"\b(?:tom tat|tom luoc|tong ket|summari[sz]e|summary of|(?:noi|viet) ve (?:cai |dieu |chuyen )?gi|"
    r"chu yeu noi ve|co (?:nhung )?noi dung gi|"
    r"what is .+ about|what's .+ about)\b"
)
QUESTION_WORDS = re.compile(
    r"\?\s*$|^(?:does|do)\b|\b(?:ai|gi|nao|bao gio|khi nao|luc nao|o dau|the nao|bao nhieu|la ai|co .+ khong|"
    r"who|what|when|where|which|how|is there|are there)\b"
)
TITLED_QUESTION_WORDS = re.compile(r"\b(?:may gio|thu may|ngay may|luc may|bao lau)\b")
FIND_ONLY = re.compile(r"\b(?:tim (?:mot |1 |cai )?(?:trang|page)|(?:trang|page) nao|which page|find (?:the )?page)\b")
DATABASE_KINDS = {"bang", "table", "database", "co so du lieu"}


@dataclass(frozen=True)
class PageQuestion:
    kind: str
    page_reference: str | None = None
    database_reference: str | None = None


def _name_after(text: Folded, start: int) -> str | None:
    rest = text.value[start:]
    if rest[:1] in QUOTES:
        close = next((index for index, char in enumerate(rest[1:], 1) if char in QUOTES), None)
        if close is None:
            return None
        return text.original(start + 1, start + close).strip() or None
    end = NAME_END.search(rest)
    stop = start + (end.start() if end else len(rest))
    name = text.original(start, stop).strip(" " + QUOTES)
    return name or None


def _known_title(text: Folded, start: int, titles: tuple[str, ...]) -> str | None:
    for title in sorted(titles, key=len, reverse=True):
        folded = fold(unicodedata.normalize("NFC", title).strip())
        end = start + len(folded)
        if folded and text.value.startswith(folded, start) and not re.match(r"\w", text.value[end:end + 1]):
            return title
    return None


def _references(text: Folded, titles: tuple[str, ...] = ()) -> tuple[str | None, str | None, bool, bool]:
    page = database = None
    current = titled = False
    for marker in MARKER.finditer(text.value):
        after = text.value[marker.end():].lstrip()
        start = len(text.value) - len(after)
        if CURRENT.match(after):
            current = True
            continue
        if NOT_A_NAME.match(after) or not after:
            continue
        known = _known_title(text, start, titles) if marker.group("kind") not in DATABASE_KINDS else None
        if known and page is None:
            page, titled = known, True
            continue
        name = _name_after(text, start)
        if not name:
            continue
        if marker.group("kind") in DATABASE_KINDS:
            database = database or name
        else:
            page = page or name
    if page is None and database is None:
        english = ENGLISH_NAME.search(text.value)
        if english:
            name = text.original(*english.span("name")).strip(" " + QUOTES)
            if english.group(0).rstrip().endswith("page"):
                page = name or None
            else:
                database = name or None
    return page, database, current, titled


def _without_task_names(source: str) -> str:
    """The sentence with named to-dos ("việc Gọi khách") blanked: their words ask nothing."""
    text = unicodedata.normalize("NFC", source)
    for start in reversed([match.end() for match in NAMED_TASK.finditer(text)]):
        if text[start:start + 1].isupper():
            end = TASK_END.search(text, start)
            text = text[:start] + "X" + text[end.start():]
    return " ".join(fold(text).split())


def _asks(text: str) -> bool:
    return bool(ASK_CUE.search(QUESTION_TAIL.sub("", text)) or ASK_CUE.search(text) and "?" in text)


def _after_page(folded: str, page: str | None, current: bool) -> str | None:
    if page:
        name = " ".join(fold(unicodedata.normalize("NFC", page)).split())
        found = folded.find(name)
        return None if found < 0 else folded[found + len(name):]
    if current:
        found = re.search(r"\b(?:trang|page) (?:nay|hien tai|dang mo)\b", folded)
        return folded[found.end():] if found else None
    return None


def _whole_page_summary(folded: str, page: str | None, current: bool) -> bool:
    after = _after_page(folded, page, current)
    if after is None:
        return False
    after = QUESTION_TAIL.sub("", after).strip(" ,")
    if SUMMARY_ASK.match(folded) and not after:
        return True
    if SUMMARY_BEFORE.search(folded) and re.fullmatch(r"la gi", after):
        return True
    return SUMMARY_AFTER.fullmatch(after) is not None


def page_question(source: str, *, has_current_page: bool, titles: tuple[str, ...] = ()) -> PageQuestion | None:
    text = Folded(unicodedata.normalize("NFC", source).strip())
    folded = " ".join(text.value.split())
    if not folded or FIND_ONLY.search(folded) or HOW_TO.match(folded) or HISTORY.search(folded):
        return None
    if EDIT_START.match(folded) or COMMA_EDIT.search(folded):
        return None
    if EDIT_START.match(fold(command_text(source)).strip()) and not ASKED_ITEM.search(folded):
        return None
    page, database, current, titled = _references(text, titles)
    named = bool(page or database or current)
    if not named and not has_current_page:
        return None
    masked = _without_task_names(source)
    asking = _asks(masked)
    if SUMMARY_WORDS.search(folded) or not database and _whole_page_summary(folded, page, current):
        if not named:
            return None
        kind = "SUMMARY"
    elif database and COUNT_WORDS.search(folded):
        kind = "DATABASE_COUNT"
    elif ONE_TASK_ASKED.match(QUESTION_TAIL.sub("", folded)) and not ASKED_ITEM.search(folded):
        kind = "FREE"
    elif (TODO_WORDS.search(folded) or TODO_ASKED_WORDS.search(folded)) and asking or TODO_LIST_ASK.match(folded):
        kind = "TODO_STATUS"
    elif COUNT_WORDS.search(folded) and re.search(r"\b(?:dong|hang|row|rows|ban ghi|record)\b", folded):
        kind = "DATABASE_COUNT"
    elif named and (QUESTION_WORDS.search(masked) or titled and TITLED_QUESTION_WORDS.search(folded)):
        kind = "FREE"
    else:
        return None
    if FOLLOW_UP_EDIT.search(folded):
        return PageQuestion("MIXED")
    return PageQuestion(kind, page, database)
