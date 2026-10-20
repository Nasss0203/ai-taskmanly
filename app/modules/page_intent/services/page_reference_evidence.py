"""Conservative surface evidence for a Page reference, never a Page lookup.

An LLM can classify an activity or a topic as a title even when the words
appear in the message. Only explicit syntactic references are treated as
TITLE. Everything uncertain remains UNRESOLVED for clarification by NestJS.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


ReferenceType = Literal["TITLE", "CURRENT_PAGE", "UNRESOLVED"]

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
    r"\b(?:thêm|chèn|sửa|chỉnh|chỉnh sửa|cập nhật|đổi|xóa|xoá|"
    r"bổ sung|ghi|viết|add|insert|edit|update|remove|delete)\b",
    re.IGNORECASE,
)
FOLLOWING_EDIT = re.compile(
    r"^(?P<title>.+?)(?:[,;]\s*|\.\s+)(?P<edit>(?:(?:rồi|sau đó|please)\s+)?"
    r"(?:hãy\s+)?(?:thêm|chèn|sửa|chỉnh|cập nhật|đổi|xóa|xoá|"
    r"bổ sung|viết|add|insert|edit|update|remove|delete)\b.*)$",
    re.IGNORECASE | re.DOTALL,
)
TRAILING_QUOTED_EDIT = re.compile(
    r"^[,;.]\s*(?P<edit>(?:(?:rồi|sau đó|please)\s+)?"
    r"(?:hãy\s+)?(?:thêm|chèn|sửa|chỉnh|cập nhật|đổi|xóa|xoá|"
    r"bổ sung|viết|add|insert|edit|update|remove|delete)\b.*)$",
    re.IGNORECASE | re.DOTALL,
)
STANDALONE_WRITING = re.compile(
    r"^(?:hãy\s+)?(?:viết lại|rút gọn|dịch|tóm tắt|cải thiện|"
    r"rewrite|translate|summarize|paraphrase)\s+"
    r"(?:câu|đoạn|văn bản|bài viết|text|sentence|paragraph|this)\b",
    re.IGNORECASE,
)


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


def _source_instruction(source: str, marker_start: int) -> str | None:
    """Keep the user's exact edit text if the page target is at the end."""
    before = source[:marker_start]
    match = EDIT_PREPOSITION.fullmatch(before)
    if not match:
        return None
    edit = match.group("edit").strip()
    return edit if EDIT_VERB.search(edit) else None


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
    markers = list(PAGE_MARKER.finditer(source))
    if not markers:
        return markers
    start = markers[0].end()
    remainder = source[start:]
    prefix = re.match(r"\s*(?:(?:(?:có\s+)?tên|named|called)\s+)?", remainder, re.IGNORECASE)
    if prefix is None:
        return markers
    quote_start = start + prefix.end()
    if quote_start >= len(source) or source[quote_start] not in {'"', "'", "`", "“", "‘"}:
        return markers
    close = {'"': '"', "'": "'", "`": "`", "“": "”", "‘": "’"}[source[quote_start]]
    quote_end = source.find(close, quote_start + 1)
    if quote_end < 0:
        return markers
    return [
        marker for marker in markers
        if not (quote_start < marker.start() < quote_end)
    ]


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
            or (evidence.instruction and not tail.strip(".!?"))
        ):
            return None
    elif FOLLOWING_EDIT.fullmatch(remainder) is None:
        return None
    return evidence


def detect_page_reference(source: str) -> PageReferenceEvidence:
    normalized = unicodedata.normalize("NFC", source).strip()
    markers = _target_markers(normalized)

    if not markers:
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
    remainder = normalized[marker.end():].strip()
    instruction = _source_instruction(normalized, marker.start())
    if not remainder:
        if ENGLISH_CURRENT_BEFORE_MARKER.search(normalized[:marker.start()]):
            return PageReferenceEvidence("CURRENT_PAGE", None, instruction)
        return PageReferenceEvidence("UNRESOLVED", None, instruction)

    if CURRENT_REFERENCE.match(remainder):
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
            if not later:
                return PageReferenceEvidence("UNRESOLVED", None, instruction)
            instruction = (
                f"{instruction} {later.group('edit').strip()}"
                if instruction else later.group("edit").strip()
            )
    else:
        trailing_edit = FOLLOWING_EDIT.match(remainder)
        if trailing_edit:
            remainder = trailing_edit.group("title").strip()
            later_instruction = trailing_edit.group("edit").strip()
            instruction = (
                f"{instruction} {later_instruction}"
                if instruction else later_instruction
            )
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
