"""Conservative surface evidence for a Page reference, never a Page lookup.

An LLM can classify an activity or a topic as a title even when the words
appear in the message. Only explicit syntactic references are treated as
TITLE. Everything uncertain remains UNRESOLVED for clarification by NestJS.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.modules.modification_planner.services.block_delete import parse_block_delete
from app.modules.modification_planner.services.block_text import parse_block_text
from app.modules.modification_planner.services.todo_status import parse_todo_status


ReferenceType = Literal["TITLE", "CURRENT_PAGE", "UNRESOLVED", "ACTIVITY", "DESCRIPTION", "CONTENT"]

PAGE_MARKER = re.compile(r"(?<!\w)(?:page|trang)(?!\w)", re.IGNORECASE)
CURRENT_REFERENCE = re.compile(
    r"^(?:này|hiện tại|đang mở|this|current)\b", re.IGNORECASE
)
ENGLISH_CURRENT_BEFORE_MARKER = re.compile(r"(?:this|current)\s+$", re.IGNORECASE)
DESCRIPTIVE_REFERENCE = re.compile(
    r"^(?:"
    r"tôi|mình|em|chúng ta|của|mà|đã|vừa|đang|mới|được|"
    r"sửa|chỉnh|tạo|xem|mở|truy cập|"
    r"hôm qua|hôm nay|gần đây|mới đây|"
    r"nói về|viết về|có chủ đề|liên quan|về|chứa|có nội dung|mô tả|"
    r"nào|nào đó|bất kỳ|khác|ở đây|là gì|"
    r"có pageid|pageid|có id|id|"
    r"i edited|i opened|about|related to|which"
    r")\b",
    re.IGNORECASE,
)
EXPLICIT_NAME = re.compile(r"^(?:(?:có\s+)?tên|named|called)\s+", re.IGNORECASE)
EDIT_PREPOSITION = re.compile(
    r"^(?P<edit>.+?)\s+(?:vào|trong|ở|trên|tại|cho|to|in|on)\s*$",
    re.IGNORECASE | re.DOTALL,
)
EDIT_VERB = re.compile(
    r"^(?:(?:hãy|vui lòng|giúp tôi|giúp mình|bạn hãy|tôi muốn|mình muốn|"
    r"please|can you|could you|would you|i want to|i need you to)\s+)*"
    r"(?:thêm|chèn|sửa|chỉnh|chỉnh sửa|cập nhật|đổi|xóa|xoá|"
    r"bổ sung|ghi|viết lại|viết|rút gọn|dịch|chép|thay thế|di chuyển|sắp xếp|định dạng|"
    r"add|insert|edit|update|remove|delete|modify|change|replace|rename|"
    r"append|prepend|move|reorder|format|rewrite|shorten|translate|copy)\b",
    re.IGNORECASE,
)
FOLLOWING_EDIT = re.compile(
    r"^(?P<title>.+?)(?:[,;]\s*|\.\s+)(?P<edit>(?:(?:rồi|sau đó|please)\s+)?"
    r"(?:hãy\s+)?(?:thêm|chèn|sửa|chỉnh|cập nhật|đổi|xóa|xoá|"
    r"bổ sung|viết|add|insert|edit|update|remove|delete)\b.*)$",
    re.IGNORECASE | re.DOTALL,
)
TRAILING_QUOTED_EDIT = re.compile(
    r"^[,;:.]?\s*(?P<edit>(?:(?:rồi|sau đó|please)\s+)?"
    r"(?:hãy\s+)?(?:thêm|chèn|sửa|chỉnh|cập nhật|đổi|xóa|xoá|"
    r"bổ sung|viết|add|insert|edit|update|remove|delete)\b.*)$",
    re.IGNORECASE | re.DOTALL,
)
# "Trong trang X thêm ..." with a bare X: only a locative (or nothing) may
# precede the Page noun, and the first edit verb after the name ends it.
LEADING_LOCATIVE = re.compile(
    r"^(?:(?:hãy|vui lòng|please)\s+)?(?:(?:trong|ở|tại|in|on|inside)\s+)?$",
    re.IGNORECASE,
)
INLINE_EDIT = re.compile(
    r"^(?P<title>.+?)\s+(?P<edit>(?:hãy\s+)?(?:thêm|chèn|sửa|chỉnh|cập nhật|đổi|xóa|xoá|"
    r"bổ sung|viết|add|insert|edit|update|remove|delete)\b.*)$",
    re.IGNORECASE | re.DOTALL,
)
STANDALONE_WRITING = re.compile(
    r"^(?:hãy\s+)?(?:viết lại|rút gọn|dịch|tóm tắt|cải thiện|"
    r"rewrite|translate|summarize|paraphrase)\s+"
    r"(?:câu|đoạn|văn bản|bài viết|text|sentence|paragraph|this)\b",
    re.IGNORECASE,
)
QUOTED_TEXT = re.compile(r'''(?<!\w)(?:"[^"]*"|'[^']*'|`[^`]*`|“[^”]*”|‘[^’]*’)''')


def is_edit_clause(text: str) -> bool:
    """An affirmative edit command, a to-do tick or a block text edit.

    Ticks may lead with the to-do's name ("gửi email xong rồi"), and ticks and
    text edits ("doi X thanh Y", "thay X bằng Y") may be typed without marks,
    so EDIT_VERB alone cannot recognise them.
    """
    return (
        bool(EDIT_VERB.match(text))
        or parse_todo_status(text) is not None
        or parse_block_text(text) is not None
        or parse_block_delete(text) is not None
    )


def mask_quoted_text(source: str) -> str:
    """Quoted titles/source text are data, not new Page markers or commands."""
    return QUOTED_TEXT.sub(lambda match: " " * len(match.group()), source)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def is_standalone_writing_request(source: str) -> bool:
    # These requests belong to Writing, not Page Modification. Only make
    # the determination when no Page target marker was supplied at all.
    text = normalize(source).strip()
    return not PAGE_MARKER.search(text) and bool(STANDALONE_WRITING.match(text))


@dataclass(frozen=True)
class PageReferenceEvidence:
    reference_type: ReferenceType
    title: str | None
    instruction: str | None
    # Only for ACTIVITY: the user's own edits that name the Page (M2).
    activity: "ActivityReference | None" = None
    # Only for TITLE: where that Page is, an ancestor Page or a teamspace (M4).
    scope: "PageScope | None" = None
    # Only for DESCRIPTION: what the Page is for, in the user's words (M6).
    description: str | None = None
    # Only for CONTENT: words inside the Page, in the user's words (M7).
    topic: str | None = None


def _source_instruction(source: str, marker_start: int) -> str | None:
    """Keep the user's exact edit text if the page target is at the end."""
    before = source[:marker_start]
    match = EDIT_PREPOSITION.fullmatch(before)
    if not match:
        return None
    edit = match.group("edit").strip()
    return edit if is_edit_clause(edit) else None


def source_backed_edit_instruction(
    source: str, evidence: PageReferenceEvidence,
) -> str | None:
    """Authorize only affirmative edit clauses present in the original input.

    Reference extraction intentionally handles a narrower grammar. Broader
    commands (e.g. 'Please modify page ...', 'Add ... to this page') may keep
    the complete source, but never borrow an operation from the model.
    Words inside Page titles cannot provide the affirmative command.
    """
    if evidence.instruction:
        return evidence.instruction
    text = unicodedata.normalize("NFC", source).strip()
    markers = _target_markers(text)
    prefix = text[:markers[0].start()].strip() if markers else text
    if not is_edit_clause(prefix):
        return None
    if re.search(r"\b(?:about|về)\s*$", prefix, re.IGNORECASE):
        return None
    # Creating a new Page does not authorize modifying an existing Page.
    if markers and re.fullmatch(
        r"(?:please\s+)?(?:add|insert)\s+(?:(?:a|another|new)\s*)*",
        prefix, re.IGNORECASE,
    ):
        return None
    return text


def is_read_only_page_request(source: str) -> bool:
    return bool(re.match(
        r"^(?:(?:please|can you|could you|hãy|vui lòng)\s+)?"
        r"(?:read|show|view|open|find|search|what|how|đọc|xem|mở|tìm|"
        r"cho (?:tôi|mình|em) xem)\b",
        normalize(source).strip(),
    ))


def _is_generic_remention(source: str, marker: re.Match[str]) -> bool:
    """A later 'cuối trang' / 'trang này' is not a second target."""
    before = source[:marker.start()]
    after = source[marker.end():].strip()
    return bool(
        re.search(r"(?:cuối|đầu|end of|start of)\s+$", before, re.IGNORECASE)
        and not after.strip(" \t\r\n.!?")
        or re.fullmatch(
            r"(?:này|hiện tại|đó|this|current)[.!?\s]*",
            after,
            re.IGNORECASE,
        )
    )


def _target_markers(source: str) -> list[re.Match[str]]:
    """Do not interpret 'page' inside an explicitly quoted title as a new target.

    Other Page references outside the title still count as multiple targets
    and must be clarified.
    """
    return list(PAGE_MARKER.finditer(mask_quoted_text(source)))


def has_multiple_page_targets(source: str) -> bool:
    markers = _target_markers(source)
    return len(markers) > 1 and any(
        not _is_generic_remention(source, marker) for marker in markers[1:]
    )


def _quoted_insertion_payload(prefix: str, tail: str) -> bool:
    """Only a block/checklist insertion + labelled, complete quoted content.

    Full matching keeps arbitrary trailing commands out of this grammar.
    The payload is data; its words never authorize an edit or another target.
    """
    command = EDIT_VERB.match(prefix)
    if not command or not re.search(
        r"(?:thêm|chèn|add|insert)$", command.group(), re.IGNORECASE,
    ):
        return False
    if not re.fullmatch(
        r"\s+(?:(?:một|1|a|one)\s+)?"
        r"(?:(?:text\s+)?block(?:\s+(?:văn bản|text))?|checklist)\s+"
        r"(?:vào|trong|ở(?:\s+(?:cuối|đầu))?|to|in|on)\s*",
        prefix[command.end():], re.IGNORECASE,
    ):
        return False
    label = re.match(r"(?:với\s+nội\s+dung|with\s+content)\s*:\s*", tail, re.IGNORECASE)
    payload = QUOTED_TEXT.match(tail, label.end()) if label else None
    return bool(
        payload and payload.group()[1:-1].strip()
        and not tail[payload.end():].strip(" .!?")
    )


def explicit_trailing_page_edit(source: str) -> PageReferenceEvidence | None:
    """Deterministic edit only for a delimited title + separate edit clause.

    Unlike generic LLM classification this is a strict, entirely source-backed
    shape. Never use this for guessed titles, descriptions or multiple Pages.
    NestJS still resolves the exact title and authorizes the target.
    """
    evidence = detect_page_reference(source)
    if evidence.reference_type != "TITLE" or not evidence.instruction:
        return None
    normalized = unicodedata.normalize("NFC", source).strip()
    markers = _target_markers(normalized)
    if not markers or any(not _is_generic_remention(normalized, marker) for marker in markers[1:]):
        return None
    remainder = normalized[markers[0].end():].strip()
    remainder = EXPLICIT_NAME.sub("", remainder).strip()
    if remainder and remainder[0] in {'"', "'", "`", "“", "‘"}:
        quote_pairs = {'"': '"', "'": "'", "`": "`", "“": "”", "‘": "’"}
        close = remainder.find(quote_pairs[remainder[0]], 1)
        tail = remainder[close + 1:].strip() if close > 0 else ""
        if close < 1 or not (
            TRAILING_QUOTED_EDIT.fullmatch(tail)
            or _quoted_insertion_payload(normalized[:markers[0].start()], tail)
            or (evidence.instruction and not tail.strip(".!?"))
        ):
            return None
    elif FOLLOWING_EDIT.fullmatch(remainder) is None:
        return None
    return evidence


def detect_page_reference(
    source: str, *, has_current_page: bool = False,
) -> PageReferenceEvidence:
    normalized = unicodedata.normalize("NFC", source).strip()
    # M8: "… dựa trên trang Bug tracker" names a source, not a second target.
    based_on = based_on_reference(normalized)
    if based_on is not None:
        normalized = based_on[0]
    markers = _target_markers(normalized)

    activity = activity_page_reference(normalized)
    if activity is not None:
        return PageReferenceEvidence("ACTIVITY", None, activity[0], activity[1])

    # M7 before M6: "trang có nói về X" holds M6's "nói về".
    content = content_page_reference(normalized)
    if content is not None:
        return PageReferenceEvidence("CONTENT", None, content[0], topic=content[1])

    # M6 before M4: "trang theo dõi lỗi của ứng dụng" describes one Page; it
    # does not name "theo dõi lỗi" inside a Page called "ứng dụng".
    described = description_page_reference(normalized)
    if described is not None:
        return PageReferenceEvidence("DESCRIPTION", None, described[0], description=described[1])

    scoped = scoped_page_reference(normalized)
    if scoped is not None:
        return PageReferenceEvidence("TITLE", scoped[1], scoped[0], scope=scoped[2])

    if not markers:
        command = EDIT_VERB.match(normalized)
        edit = (command and normalized[command.end():].strip()) or parse_todo_status(normalized)
        if has_current_page and edit and not is_standalone_writing_request(normalized):
            return PageReferenceEvidence("CURRENT_PAGE", None, normalized)
        return PageReferenceEvidence("UNRESOLVED", None, None)

    # Multiple mentions cannot safely be resolved without deeper discourse
    # analysis, even when the LLM picks one of the mentioned names.
    if len(markers) != 1 and not all(
        _is_generic_remention(normalized, later) for later in markers[1:]
    ):
        return PageReferenceEvidence(
            "UNRESOLVED", None, _source_instruction(normalized, markers[0].start())
        )

    marker = markers[0]
    # English explicitly puts the quoted title before the Page noun.
    before = normalized[:marker.start()].rstrip()
    quoted = list(QUOTED_TEXT.finditer(before))
    if marker.group().casefold() == "page" and quoted and quoted[-1].end() == len(before):
        title_match = quoted[-1]
        prefix = before[:title_match.start()]
        edit = re.fullmatch(r"(.+?)\s+(?:to|in|on)\s+(?:the\s+)?", prefix, re.IGNORECASE)
        if edit and EDIT_VERB.match(edit.group(1)) and not normalized[marker.end():].strip(" .!?"):
            return PageReferenceEvidence("TITLE", title_match.group()[1:-1].strip(), edit.group(1).strip())
    remainder = normalized[marker.end():].strip()
    instruction = _source_instruction(normalized, marker.start())
    if instruction:
        remainder = re.sub(r"\s+(?:nhé|nha|ạ)[.!?\s]*$", "", remainder, flags=re.IGNORECASE)
    if not remainder:
        if ENGLISH_CURRENT_BEFORE_MARKER.search(normalized[:marker.start()]):
            return PageReferenceEvidence("CURRENT_PAGE", None, instruction)
        return PageReferenceEvidence("UNRESOLVED", None, instruction)

    if CURRENT_REFERENCE.match(remainder):
        following = CURRENT_REFERENCE.match(remainder)
        tail = remainder[following.end():].lstrip(" ,;:.")
        if (not normalized[:marker.start()].strip()
                and is_edit_clause(tail)):
            return PageReferenceEvidence("CURRENT_PAGE", None, tail)
        # Only an exact current-page phrase is strong evidence.
        if re.fullmatch(
            r"(?:này|hiện tại|đang mở|this|current)[.!?\s]*",
            remainder,
            re.IGNORECASE,
        ):
            return PageReferenceEvidence("CURRENT_PAGE", None, instruction)
        return PageReferenceEvidence("UNRESOLVED", None, instruction)

    if DESCRIPTIVE_REFERENCE.match(remainder):
        return PageReferenceEvidence("UNRESOLVED", None, instruction)

    explicitly_named = bool(EXPLICIT_NAME.match(remainder))
    remainder = EXPLICIT_NAME.sub("", remainder).strip()
    if not remainder:
        return PageReferenceEvidence("UNRESOLVED", None, instruction)

    # Quotation explicitly delimits a multi-word title.
    quote_pairs = {'"': '"', "'": "'", "`": "`", "“": "”", "‘": "’"}
    quoted = remainder[0] in quote_pairs
    if quoted:
        close = quote_pairs[remainder[0]]
        end = remainder.find(close, 1)
        if end <= 1:
            return PageReferenceEvidence("UNRESOLVED", None, instruction)
        title = remainder[1:end].strip()
        tail = remainder[end + 1:].strip()
        if tail and tail.strip(".!?"):
            later = TRAILING_QUOTED_EDIT.fullmatch(tail)
            if _quoted_insertion_payload(normalized[:marker.start()], tail):
                # Keep the original source, including position, quoting and
                # payload; the prefix alone would lose the content.
                instruction = source
            elif not later:
                # Whole-Page rewrite/translate/rename is an intent only. Keep
                # the complete source so no requested replacement is lost.
                direct = normalized[:marker.start()].strip()
                if (EDIT_VERB.match(direct)
                        and re.match(r"^(?:cho|thành|sang|to|for)\b", tail, re.IGNORECASE)):
                    instruction = normalized
                else:
                    return PageReferenceEvidence("UNRESOLVED", None, instruction)
            else:
                instruction = (
                    f"{instruction} {later.group('edit').strip()}"
                    if instruction else later.group("edit").strip()
                )
    else:
        trailing_edit = FOLLOWING_EDIT.match(remainder)
        inline_edit = (
            INLINE_EDIT.match(remainder)
            if not trailing_edit and not instruction
            and LEADING_LOCATIVE.match(normalized[:marker.start()])
            else None
        )
        if trailing_edit:
            remainder = trailing_edit.group("title").strip()
            later_instruction = trailing_edit.group("edit").strip()
            instruction = (
                f"{instruction} {later_instruction}"
                if instruction else later_instruction
            )
        elif inline_edit:
            remainder = inline_edit.group("title").strip()
            instruction = inline_edit.group("edit").strip()
        elif "," in remainder or ";" in remainder:
            # A bare title containing punctuation must be quoted to avoid
            # accidentally swallowing instructions into the Page name.
            return PageReferenceEvidence("UNRESOLVED", None, instruction)
        # A bare title is accepted only when it completes the reference,
        # not when it is followed by another editing clause.
        title = remainder.rstrip(" \t\r\n.!?").strip()
        if re.search(r"\s+(?:hoặc|or)\s+", title, re.IGNORECASE):
            return PageReferenceEvidence("UNRESOLVED", None, instruction)

    if (
        not title
        or (not quoted and not explicitly_named and DESCRIPTIVE_REFERENCE.match(title))
        or CURRENT_REFERENCE.match(title)
        or re.search(r"\s+(?:rồi|sau đó|để|then)\s+", title, re.IGNORECASE)
    ):
        return PageReferenceEvidence("UNRESOLVED", None, instruction)

    return PageReferenceEvidence("TITLE", title, instruction)


# M2 (kế hoạch tìm theo hoạt động, B1): "… vào trang [gợi ý] tôi sửa hôm qua"
# names a Page by the user's own edits, not by its title. Only the words are
# taken here; NestJS turns the time into dates in the user's time zone.
ActivityRelative = Literal["LATEST", "TODAY", "YESTERDAY", "N_DAYS_AGO", "LAST_WEEK", "RECENT"]
MAX_ACTIVITY_DAYS = 30
MAX_HINT_WORDS = 5


@dataclass(frozen=True)
class ActivityReference:
    relative: ActivityRelative
    days: int | None = None
    title_hint: str | None = None


ACTIVITY_VI = re.compile(
    r"^(?P<edit>.+?)\s+(?:vào|trong|ở|trên|tại|cho)\s+(?:trang|page)\s+"
    r"(?:(?P<hint>.+?)\s+)?(?:(?:mà|do)\s+)?(?:tôi|mình|em)\s+"
    r"(?P<just>(?:(?:vừa|mới|đã)\s+)*)(?:chỉnh sửa|sửa|chỉnh|cập nhật|viết)"
    r"(?:\s+(?P<time>.+?))?$",
    re.IGNORECASE | re.DOTALL,
)
ACTIVITY_EN = re.compile(
    r"^(?P<edit>.+?)\s+(?:to|in|on|into)\s+(?:the\s+)?(?:(?P<hint>.+?)\s+)?page\s+"
    r"(?:that\s+)?i\s+(?P<just>(?:(?:last|just|recently)\s+)*)"
    r"(?:edited|updated|changed|modified|worked on)(?:\s+(?P<time>.+?))?$",
    re.IGNORECASE | re.DOTALL,
)
ACTIVITY_TIMES: tuple[tuple[re.Pattern[str], ActivityRelative], ...] = (
    (re.compile(r"^(?:gần đây nhất|gần nhất|lần cuối|lần gần nhất|mới nhất|cuối cùng|most recently|last)$"), "LATEST"),
    (re.compile(r"^(?:hôm nay|today)$"), "TODAY"),
    (re.compile(r"^(?:hôm qua|yesterday)$"), "YESTERDAY"),
    (re.compile(r"^(?:tuần trước|last week)$"), "LAST_WEEK"),
    (re.compile(r"^(?:gần đây|dạo này|recently|lately)$"), "RECENT"),
)
DAYS_AGO = re.compile(r"^(?P<days>\d{1,2})\s+(?:ngày trước|days? ago)$")
ACTIVITY_TAIL = re.compile(r"(?:[\s,]+(?:nhé|nha|ạ|please))*[\s.!?]*$", re.IGNORECASE)


def _activity_time(time: str | None, just: str) -> ActivityReference | None:
    words = normalize(" ".join((time or "").split()))
    adverbs = normalize(just).split()
    if not words:
        # "trang tôi vừa sửa" / "the page I last edited": the latest one.
        if {"vừa", "mới", "last", "just"} & set(adverbs):
            return ActivityReference("LATEST")
        if "recently" in adverbs:
            return ActivityReference("RECENT")
        return None
    if words == "hôm kia":
        return ActivityReference("N_DAYS_AGO", 2)
    days = DAYS_AGO.match(words)
    if days:
        count = int(days.group("days"))
        return ActivityReference("N_DAYS_AGO", count) if 1 <= count <= MAX_ACTIVITY_DAYS else None
    for pattern, relative in ACTIVITY_TIMES:
        if pattern.match(words):
            return ActivityReference(relative)
    return None


def activity_page_reference(source: str) -> tuple[str, ActivityReference] | None:
    """The edit clause and the activity a sentence names its Page by, if any."""
    text = ACTIVITY_TAIL.sub("", unicodedata.normalize("NFC", source).strip())
    if len(_target_markers(text)) != 1:
        return None
    for pattern in (ACTIVITY_VI, ACTIVITY_EN):
        match = pattern.match(text)
        if not match:
            continue
        edit = match.group("edit").strip()
        reference = _activity_time(match.group("time"), match.group("just") or "")
        if reference is None or not is_edit_clause(edit):
            return None
        # "trang mà tôi sửa": "mà" / "do" only joins the clause, it names nothing.
        hint = re.sub(r"(?:^|\s+)(?:mà|do|that)$", "", (match.group("hint") or "").strip(), flags=re.IGNORECASE)
        hint = hint.strip().strip("\"'“”‘’`").strip()
        if hint and len(hint.split()) > MAX_HINT_WORDS:
            return None
        return edit, ActivityReference(reference.relative, reference.days, hint or None)
    return None


# M4 (kế hoạch lọc theo cấu trúc, E1–E2): "… vào trang Tasks trong trang Dự án A"
# names one Page and where it is: an ancestor Page, or a teamspace. There is no
# project entity: "dự án A" is the words of an ancestor Page's title.
MAX_SCOPED_NAME_WORDS = 8


@dataclass(frozen=True)
class PageScope:
    parent_title: str | None = None
    teamspace_name: str | None = None


SCOPE_VI = re.compile(
    r"^(?P<edit>.+?)\s+(?:vào|trong|ở|trên|tại|cho)\s+trang\s+(?P<title>.+?)\s+"
    r"(?:"
    # "trong" needs the kind of place: "trang Tasks trong tuần này" names no Page.
    r"trong\s+(?P<kind>trang|dự án|teamspace)\s+(?P<name>.+?)"
    r"|(?:của|thuộc)\s+(?:(?P<kind2>trang|dự án|teamspace)\s+)?(?P<name2>.+?)"
    r")$",
    re.IGNORECASE | re.DOTALL,
)
SCOPE_EN = re.compile(
    r"^(?P<edit>.+?)\s+(?:to|in|on|into)\s+(?:the\s+)?(?P<title>.+?)\s+page\s+"
    r"(?:in|of|under|inside)\s+(?:the\s+)?"
    r"(?:(?P<kind>project|teamspace)\s+(?P<name>.+?)|(?P<name2>.+?)\s+(?P<kind2>page|project|teamspace))$",
    re.IGNORECASE | re.DOTALL,
)
SCOPE_TAIL = re.compile(r"(?:[\s,]+(?:nhé|nha|ạ|please))*[\s.!?]*$", re.IGNORECASE)
QUOTE_CHARS = "\"'“”‘’`"


# "của workspace khác" never names a place inside this workspace, and "của tôi"
# describes the Page rather than naming its ancestor.
NOT_A_PLACE = re.compile(r"^(?:workspace|không gian làm việc|other workspace)\b", re.IGNORECASE)


def _scoped_name(text: str | None) -> str | None:
    name = (text or "").strip().strip(QUOTE_CHARS).strip()
    if (not name or len(name.split()) > MAX_SCOPED_NAME_WORDS or PAGE_MARKER.search(name)
            or NOT_A_PLACE.match(name) or DESCRIPTIVE_REFERENCE.match(name)):
        return None
    return name


def scoped_page_reference(source: str) -> tuple[str, str, PageScope] | None:
    """The edit clause, the Page name and where that Page is, if a sentence says so."""
    text = SCOPE_TAIL.sub("", unicodedata.normalize("NFC", source).strip())
    for pattern in (SCOPE_VI, SCOPE_EN):
        match = pattern.match(text)
        if not match:
            continue
        edit = match.group("edit").strip()
        title = _scoped_name(match.group("title"))
        kind = normalize(match.group("kind") or match.group("kind2") or "")
        name = _scoped_name(match.group("name") or match.group("name2"))
        if not (title and name and is_edit_clause(edit)):
            return None
        if kind == "teamspace":
            return edit, title, PageScope(teamspace_name=name)
        # "dự án A" / "project A": NestJS tries "A" and the whole words.
        if kind in ("dự án", "project"):
            name = f"{match.group('kind') or match.group('kind2')} {name}"
        return edit, title, PageScope(parent_title=name)
    return None


# M6 (kế hoạch tìm theo mô tả, G1): "… vào trang dùng để chuẩn bị phát hành"
# names a Page by what it is for, not by its title. NestJS looks for Pages
# close to the description and always lets the user pick one.
MIN_DESCRIPTION_WORDS = 2
MAX_DESCRIPTION_WORDS = 20

# "ghi chú" is a word of its own (a note), not "ghi" (records) + a description.
DESCRIPTION_CUE_VI = (
    r"(?:dùng để|dùng cho|để|nói về|viết về|về|ghi lại|ghi chép|ghi(?!\s+chú\b)|"
    r"theo dõi|liên quan (?:đến|tới)|chuyên về)"
)
DESCRIPTION_CUE_EN = (
    r"(?:about|for|on|covering|used for|that (?:covers|tracks|is about)|"
    r"where (?:we|i) (?:track|keep|write down|write))"
)
DESCRIPTION_VI = re.compile(
    r"^(?P<edit>.+?)\s+(?:vào|trong|ở|trên|tại|cho)\s+trang\s+"
    rf"{DESCRIPTION_CUE_VI}\s+(?P<description>.+?)$",
    re.IGNORECASE | re.DOTALL,
)
# "Sửa trang dùng để …: thêm …" puts the edit after the description.
DESCRIPTION_VI_FIRST = re.compile(
    r"^(?:(?:hãy|vui lòng)\s+)?(?:sửa|chỉnh sửa|chỉnh|cập nhật)\s+trang\s+"
    rf"{DESCRIPTION_CUE_VI}\s+(?P<description>[^:,;]+?)\s*[:,;]\s*(?P<edit>.+)$",
    re.IGNORECASE | re.DOTALL,
)
DESCRIPTION_EN = re.compile(
    r"^(?P<edit>.+?)\s+(?:to|in|on|into)\s+the\s+page\s+"
    rf"{DESCRIPTION_CUE_EN}\s+(?P<description>.+?)$",
    re.IGNORECASE | re.DOTALL,
)
DESCRIPTION_EN_FIRST = re.compile(
    r"^(?:please\s+)?(?:edit|update)\s+the\s+page\s+"
    rf"{DESCRIPTION_CUE_EN}\s+(?P<description>[^:,;]+?)\s*[:,;]\s*(?P<edit>.+)$",
    re.IGNORECASE | re.DOTALL,
)
DESCRIPTION_TAIL = re.compile(r"(?:[\s,]+(?:nhé|nha|ạ|please))*[\s.!?]*$", re.IGNORECASE)


def description_page_reference(source: str) -> tuple[str, str] | None:
    """The edit clause and the description a sentence names its Page by, if any."""
    text = DESCRIPTION_TAIL.sub("", unicodedata.normalize("NFC", source).strip())
    # One Page only, and a quoted name is a title, never a description.
    if len(_target_markers(text)) != 1 or QUOTED_TEXT.search(text):
        return None
    for pattern in (DESCRIPTION_VI, DESCRIPTION_VI_FIRST, DESCRIPTION_EN, DESCRIPTION_EN_FIRST):
        match = pattern.match(text)
        if not match:
            continue
        edit = DESCRIPTION_TAIL.sub("", match.group("edit").strip())
        description = match.group("description").strip()
        words = len(description.split())
        if (not MIN_DESCRIPTION_WORDS <= words <= MAX_DESCRIPTION_WORDS
                or not is_edit_clause(edit)):
            return None
        return edit, description
    return None


# M7 (kế hoạch tìm theo nội dung, H1): "… vào trang có nhắc tới OAuth" and
# "Tìm trang có nói về OAuth rồi thêm …" name a Page by words inside it.
# NestJS offers the Pages whose text is closest, each with the matching words.
MAX_TOPIC_WORDS = 20

CONTENT_CUE_VI = (
    r"(?:có nói về|có nhắc tới|có nhắc đến|có nhắc|có ghi(?!\s+chú\b)|có chứa|chứa|"
    r"có nội dung|có đoạn(?:\s+nói về)?)"
)
CONTENT_CUE_EN = r"(?:that mentions|that talks about|that contains|mentioning|containing)"
CONTENT_VI = re.compile(
    r"^(?P<edit>.+?)\s+(?:vào|trong|ở|trên|tại|cho)\s+(?:trang|page)\s+"
    rf"{CONTENT_CUE_VI}\s+(?P<topic>.+?)$",
    re.IGNORECASE | re.DOTALL,
)
# "Tìm trang có nói về OAuth rồi thêm …": the Page first, then the edit.
CONTENT_VI_FIND = re.compile(
    r"^(?:(?:hãy|bạn hãy|giúp tôi|giúp mình)\s+)?tìm\s+(?:(?:một|1|cái)\s+)?(?:trang|page)\s+"
    rf"(?:nào\s+)?{CONTENT_CUE_VI}\s+(?P<topic>[^,;:]+?)"
    r"(?:\s*[,;:]\s*(?:(?:rồi|sau đó|xong)\s+)?|\s+(?:rồi|sau đó)\s+)(?P<edit>.+)$",
    re.IGNORECASE | re.DOTALL,
)
CONTENT_EN = re.compile(
    r"^(?P<edit>.+?)\s+(?:to|in|on|into)\s+the\s+page\s+"
    rf"{CONTENT_CUE_EN}\s+(?P<topic>.+?)$",
    re.IGNORECASE | re.DOTALL,
)
CONTENT_EN_FIND = re.compile(
    rf"^(?:please\s+)?find\s+the\s+page\s+{CONTENT_CUE_EN}\s+(?P<topic>[^,;:]+?)"
    r"(?:\s*[,;:]\s*(?:then\s+)?|\s+(?:and then|then|and)\s+)(?P<edit>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def content_page_reference(source: str) -> tuple[str, str] | None:
    """The edit clause and the words a sentence finds its Page by, if any."""
    text = DESCRIPTION_TAIL.sub("", unicodedata.normalize("NFC", source).strip())
    # One Page only, and a quoted name is a title, never words inside a Page.
    if len(_target_markers(text)) != 1 or QUOTED_TEXT.search(text):
        return None
    for pattern in (CONTENT_VI, CONTENT_VI_FIND, CONTENT_EN, CONTENT_EN_FIND):
        match = pattern.match(text)
        if not match:
            continue
        edit = DESCRIPTION_TAIL.sub("", match.group("edit").strip())
        topic = match.group("topic").strip()
        # One word is enough: "có nhắc tới OAuth" already says what it is.
        if not 1 <= len(topic.split()) <= MAX_TOPIC_WORDS or not is_edit_clause(edit):
            return None
        return edit, topic
    return None


# M8 (kế hoạch ngữ cảnh RAG, I2): "… dựa trên trang Bug tracker" / "… dựa
# trên ghi chú QA gần đây" says where the draft's facts come from. It names a
# source to read, never the target Page or an edit.
MAX_BASED_ON_WORDS = 12

BASED_ON = re.compile(
    r"^(?P<rest>.+?)\s*,?\s+(?:dựa trên|dựa vào|căn cứ vào|"
    r"theo nội dung(?:\s+(?:của|trong))?|tham khảo|based on|according to)\s+"
    r"(?P<source>.+?)$",
    re.IGNORECASE | re.DOTALL,
)
# "tài liệu tham khảo vào trang X": the cue word is a noun, the source a place.
NOT_A_SOURCE = re.compile(r"^(?:vào|trong|ở|trên|tại|cho|to|in|on|into)\b", re.IGNORECASE)


def based_on_reference(source: str) -> tuple[str, str] | None:
    """The sentence without its source, and the source, if the user named one."""
    text = DESCRIPTION_TAIL.sub("", unicodedata.normalize("NFC", source).strip())
    match = BASED_ON.match(text)
    if not match:
        return None
    rest = match.group("rest").strip().rstrip(",").strip()
    named = match.group("source").strip()
    if (not 1 <= len(named.split()) <= MAX_BASED_ON_WORDS
            or NOT_A_SOURCE.match(named) or not rest):
        return None
    return rest, named
