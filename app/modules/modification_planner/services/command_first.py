import re
import unicodedata
from dataclasses import dataclass

from app.shared.vi_vocabulary import words

FILLERS = ("bạn ơi", "nhờ bạn", "giúp mình", "giúp tôi", "giùm mình", "bạn", "mình", "tôi", "em", "hãy", "nhớ là", "nhớ")
TRAILING = ("giúp mình", "giùm mình", "giúp tôi", "giúp", "giùm", "hộ", "nhé", "nha", "đi", "với", "nữa", "luôn")
PRONOUNS = {"nó", "đó", "này", "vào", "lại", "đi", "luôn", "cho mình", "vào đó"}
POINTING = {"đó", "này", "kia", "ấy", "nọ"}
TITLE_STOP = {
    "có", "thiếu", "còn", "chưa", "thêm", "cần", "mình", "bạn", "tôi", "em", "xong", "đã", "làm", "thừa", "không",
    "phần", "mục", "bảng", "việc", "ghi", "cho", "đưa", "note", "viết", "đặt", "để", "bỏ", "xoá", "xóa", "tích",
    "check", "đánh", "coi", "sửa", "đổi", "ở", "trong", "nhé", "nha", "giúp", "giùm", "hộ", "với", "thì", "nên",
    "muốn", "của", "vào", "khỏi", "chỗ", "dòng", "gỡ", "chèn", "bổ",
}
PAGE_PREP = r"(?:ở|trong|tại|vào|của|trên|khỏi)"
EDGE = r"(?:dưới cùng|cuối cùng|cuối|đầu)"
CREATE_LEAD = re.compile(r"^(?:tạo|lập|làm|dựng|soạn)\b")
SPLIT = re.compile(r"(\s*[,:;]\s+|\s+(?:thì|nên)\s+)")
QUESTION = {"nào", "gì", "sao", "bao nhiêu", "chưa", "không"}
EDGE_AFTER = re.compile(rf"\s+ở\s+(?P<edge>{EDGE})$")


def _alternatives(*groups: str) -> list[str]:
    found = [unicodedata.normalize("NFC", word).lower() for word in words(*groups, marked=True)]
    return sorted(set(found), key=lambda word: (-len(word), word))


VERBS = [(word, "untick") for word in _alternatives("verb_untick_said")] + \
    [(word, "insert_said") for word in _alternatives("verb_insert_said")] + \
    [(word, "delete_said") for word in _alternatives("verb_delete_said")] + \
    [(word, "tick") for word in _alternatives("verb_tick")] + \
    [(word, "delete") for word in _alternatives("verb_delete")] + \
    [(word, "insert") for word in _alternatives("verb_insert")] + \
    [(word, "edit") for word in _alternatives("verb_edit")]
VERBS.sort(key=lambda pair: -len(pair[0]))
STATES = sorted([(word, kind) for kind, group in (("tick", "state_tick"), ("untick", "state_untick"),
                                                  ("delete", "state_delete"))
                 for word in _alternatives(group)], key=lambda pair: -len(pair[0]))
WANTS = _alternatives("state_insert")
REMIND = _alternatives("remind_lead")


@dataclass
class Clause:
    kind: str = "plain"
    verb: str = ""
    family: str = ""
    obj: str = ""
    page: str = ""
    edge: str = ""
    container: str = ""
    new_text: str = ""


def _starts(text: str, word: str) -> bool:
    return text == word or text.startswith(word + " ")


def _ends(text: str, word: str) -> bool:
    return text == word or text.endswith(" " + word)


def _strip_fillers(text: str) -> str:
    changed = True
    while changed and text:
        changed = False
        low = text.lower()
        for word in FILLERS:
            if _starts(low, word):
                text, changed = text[len(word):].strip(), True
                break
        low = text.lower()
        for word in TRAILING:
            if _ends(low, word) and len(text) > len(word):
                text, changed = text[:len(text) - len(word)].strip(), True
                break
    return text


def _verb_at(text: str) -> tuple[str, str] | None:
    low = text.lower()
    for word, family in VERBS:
        if _starts(low, word):
            return word, family
    return None


def _take_page(text: str) -> tuple[str, str, str] | None:
    found = re.search(rf"(?:(?<=\s)|^)(?:{PAGE_PREP}\s+)?(?:(?P<edge>{EDGE})\s+(?:của\s+)?)?trang\s+(?P<title>\S.*)$",
                      text, re.IGNORECASE)
    if found is None:
        return None
    title_words = []
    for word in found.group("title").split():
        if word.lower() in TITLE_STOP:
            break
        title_words.append(word)
    if not title_words:
        return None
    title = " ".join(title_words)
    start = found.start()
    end = found.start("title") + len(title)
    rest = (text[:start] + " " + text[end:]).strip()
    return f"trang {title}", (found.group("edge") or "").lower(), re.sub(r"\s+", " ", rest)


def _take_container(text: str) -> tuple[str, str]:
    found = re.search(r"(?:(?<=\s)|^)(?:(?:vào|ở|trong|dưới)\s+)?(?P<kind>bảng|mục|phần)\s+(?P<name>\S.*)$",
                      text, re.IGNORECASE)
    if found is None:
        return "", text
    name_words = []
    for word in found.group("name").split():
        if word.lower() in TITLE_STOP:
            break
        name_words.append(word)
    if not name_words:
        return "", text
    name = " ".join(name_words)
    end = found.start("name") + len(name)
    rest = (text[:found.start()] + " " + text[end:]).strip()
    return f"{found.group('kind')} {name}", re.sub(r"\s+", " ", rest)


def _object(text: str) -> str:
    text = _strip_fillers(text.strip())
    text = re.sub(r"^(?:về|còn)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:mình|tôi|em)(?:\s+(?:chưa|đã|vừa))?(?:\s+(?:ghi|có|thêm))?$", "", text, flags=re.IGNORECASE)
    text = _strip_fillers(text)
    return "" if text.lower() in PRONOUNS else text


def _parse(text: str) -> Clause:
    clause = Clause()
    text = _strip_fillers(text.strip())
    edge_after = EDGE_AFTER.search(text)
    if edge_after:
        clause.edge = edge_after.group("edge").lower()
        text = text[:edge_after.start()].strip()
    verb = _verb_at(text)
    if verb:
        word, family = verb
        clause.kind, clause.verb, clause.family = "verb", text[:len(word)], family
        rest = text[len(word):].strip()
        page = _take_page(rest)
        if page:
            clause.page, edge, rest = page
            clause.edge = clause.edge or edge
        clause.container, rest = _take_container(rest)
        if family == "edit":
            changed = re.match(r"^(?:lại\s+)?thành\s+(?P<new>.+)$", rest, re.IGNORECASE)
            if changed is not None:
                clause.new_text = changed.group("new").strip()
                return clause
        clause.obj = _object(re.sub(r"^(?:vào|lại)(?:\s+|$)", "", rest, flags=re.IGNORECASE))
        return clause
    page = _take_page(text)
    if page:
        clause.page, edge, text = page
        clause.edge = clause.edge or edge
    clause.container, text = _take_container(text)
    if not clause.page:
        page = _take_page(text)
        if page:
            clause.page, edge, text = page
            clause.edge = clause.edge or edge
    text = _strip_fillers(text)
    low = text.lower()
    for word in WANTS:
        if _starts(low, word):
            clause.kind, clause.family, clause.obj = "state", "insert", _object(text[len(word):])
            return clause
    verb = _verb_at(text)
    if verb:
        word, family = verb
        clause.kind, clause.verb, clause.family = "verb", text[:len(word)], family
        rest = text[len(word):].strip()
        if family == "edit":
            changed = re.match(r"^(?:lại\s+)?thành\s+(?P<new>.+)$", rest, re.IGNORECASE)
            if changed is None:
                clause.obj = _object(rest)
                return clause
            clause.new_text = changed.group("new").strip()
            return clause
        clause.obj = _object(re.sub(r"^(?:vào|lại)\s+", "", rest, flags=re.IGNORECASE))
        return clause
    edit = re.search(r"\s(?P<verb>sửa|đổi|thay)(?:\s+lại)?\s+thành\s+(?P<new>.+)$", text, re.IGNORECASE)
    if edit:
        clause.kind, clause.verb, clause.family = "verb", edit.group("verb"), "edit"
        clause.obj = _object(re.sub(r"^(?:chỗ|dòng)\s+", "", text[:edit.start()].strip(), flags=re.IGNORECASE))
        clause.new_text = edit.group("new").strip()
        return clause
    for word, family in STATES:
        if _ends(low, word):
            clause.kind, clause.family = "state", family
            clause.obj = _object(text[:len(text) - len(word)].strip())
            return clause
    clause.obj = _object(text)
    return clause


def _verb_word(clause: Clause) -> str:
    family, verb = clause.family, clause.verb
    if family in ("insert", "tick", "delete", "edit") and verb:
        return verb
    return {"insert_said": "thêm", "insert": "thêm", "delete_said": "xoá", "delete": "xoá",
            "tick": "tích", "untick": "bỏ tích"}[family]


def _named(obj: str) -> str:
    return re.sub(r"^(?:có\s+)?(?:việc|to-do|todo|dòng|chỗ)\s+", "", obj, flags=re.IGNORECASE)


def command_first(text: str) -> str:
    sentence = unicodedata.normalize("NFC", text).strip()
    low = sentence.lower()
    if "?" in sentence or "\x00" in sentence or CREATE_LEAD.match(low):
        return text
    for word in REMIND:
        if _starts(low, word) and _verb_at(sentence[len(word):].strip()):
            return sentence[len(word):].strip()
    if _verb_at(sentence):
        return text
    pieces = SPLIT.split(sentence)
    parts = [piece for piece in pieces[0::2]]
    joins = [piece.strip() for piece in pieces[1::2]]
    if any(part.lower().split()[-1:] and part.lower().split()[-1] in QUESTION for part in parts if part.strip()):
        return text
    if any(word in QUESTION - {"chưa", "không"} for word in low.split()):
        return text
    clauses = [_parse(part) for part in parts]
    commands = [index for index, clause in enumerate(clauses) if clause.kind == "verb"]
    states = [index for index, clause in enumerate(clauses) if clause.kind == "state"]
    pages = {clause.page.lower() for clause in clauses if clause.page}
    if len(commands) > 1 or len(pages) != 1 or len(states) > 1 or not (commands or states):
        return text
    page = next(clause.page for clause in clauses if clause.page)
    if page.split(" ", 1)[1].lower() in POINTING or page.split(" ", 2)[1].lower() == "mới":
        return text
    at = commands[0] if commands else states[0]
    command = clauses[at]
    if command.kind == "state" and command.family in ("tick", "untick") and not command.page:
        return text
    if command.kind == "verb" and command.obj and any(join not in (",", "") for join in joins[at:]):
        return text
    if (command.kind == "verb" and not command.obj and command.page and not command.new_text
            and not command.verb.lower().endswith(("vào", "khỏi"))):
        part = parts[at].lower()
        verb_end = part.find(command.verb.lower()) + len(command.verb)
        if re.match(r"^\s*(?:luôn\s+)?trang\b", part[verb_end:]):
            return text
    obj = command.obj
    if command.kind == "verb" and states:
        if obj:
            return text
        obj = clauses[states[0]].obj
    if not obj:
        before = [clauses[i].obj for i in range(at) if clauses[i].kind == "plain" and clauses[i].obj]
        obj = before[-1] if before else ""
    elif command.kind == "verb" and any(clauses[i].kind == "plain" and clauses[i].obj for i in range(at)):
        return text
    after = [clauses[i].obj for i in range(at + 1, len(clauses))
             if clauses[i].kind == "plain" and clauses[i].obj and not clauses[i].page]
    if command.family in ("insert", "insert_said") and after:
        obj = ", ".join([obj, *after]) if obj else ""
    if not obj or re.search(r"(?<!\w)trang(?!\w)", obj, re.IGNORECASE):
        return text
    container = next((clause.container for clause in clauses if clause.container), "")
    edge = next((clause.edge for clause in clauses if clause.edge), "")
    place = f"{'cuối' if edge in ('dưới cùng', 'cuối cùng', 'cuối') else edge} {page}".strip()
    verb = _verb_word(command)
    if command.family == "edit":
        if not command.new_text:
            return text
        return f"{verb} {_named(obj)} thành {command.new_text} ở {place}"
    if command.family in ("insert", "insert_said"):
        if container:
            return f"{verb} {obj} vào {container} ở {place}"
        return f"{verb} {obj} vào {place}"
    if command.family in ("tick", "untick") and command.kind == "state" and clauses[at].family == "untick":
        verb = "bỏ tích"
    return f"{verb} {_named(obj)} ở {place}"
