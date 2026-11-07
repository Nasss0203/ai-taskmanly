"""Ask back when the named section or table is not on the Page (bộ đo gp15, gp25, gp29).

"thêm to-do X vào phần Môn Sinh" on a Page without "Môn Sinh": the model put it
under another heading; "thêm dòng vào bảng Chi tiêu" wrote into another table.
Only an explicit target ("vào/trong/dưới/ở phần|mục|bảng X", "under/in/to the X
section|table") is checked. A name found in any block text or database name
leaves the sentence to the planner, and a truncated context is never called missing.
"""

import re
from typing import Any

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    AiPageContext,
)
from app.modules.modification_planner.services.sentence_text import QUOTES, Folded, command_text, text_key
from app.modules.modification_planner.services.todo_status import PLAN_ADAPTER

MISSING_TARGET_MODEL = "missing-target-v1"
LISTED_TARGETS = 10

# Matched on the folded sentence (no marks, "đ" -> "d").
_VI_NAME = r"(?P<name>[^,.:;!?]+?)"
_VI_END = r"(?=\s+(?:voi|co|gom|bao gom|kem|nhu sau)\b|\s*[,.:;!?]|\s*$)"
# An English name never spans a joined clause ("to the Workouts table and a heading").
_EN_NAME = (
    r"(?P<name>(?:(?!\b(?:to|in|into|under|after|before|below|above|the|and|a|an"
    r"|table|database|section|heading)\b)[^,.:;!?])+?)"
)
SECTION = (
    re.compile(
        r"\b(?:vao|trong|duoi|o|sau|truoc)\s+(?:(?:trong|duoi)\s+)?(?:phan|muc)\s+" + _VI_NAME + _VI_END,
    ),
    re.compile(
        r"\b(?:under|in|into|to|after|before|below|above)\s+the\s+" + _EN_NAME + r"\s+(?:section|heading)\b",
    ),
)
TABLE = (
    re.compile(r"\b(?:vao|trong|o)\s+(?:bang|database|csdl)\s+" + _VI_NAME + _VI_END),
    re.compile(r"\b(?:to|in|into)\s+the\s+" + _EN_NAME + r"\s+(?:table|database)\b"),
)


def _named(patterns: tuple[re.Pattern[str], ...], command: Folded) -> str | None:
    for pattern in patterns:
        match = pattern.search(command.value)
        if match:
            name = command.original(*match.span("name")).strip(" " + QUOTES)
            if text_key(name):
                return name
    return None


def _contains(text: str, name: str) -> bool:
    return f" {text_key(name)} " in f" {text_key(text)} "


def _listed(names: list[str], empty: str) -> str:
    if not names:
        return f" {empty}"
    more = "…" if len(names) > LISTED_TARGETS else ""
    return f" Đang có: {', '.join(names[:LISTED_TARGETS])}{more}."


def _ask(context: AiPageContext, description: str, question: str) -> AiModificationPlan:
    return PLAN_ADAPTER.validate_python({
        "schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": context.page.id,
        "status": "NEED_MORE_CONTEXT", "summary": "Không thấy vị trí cần thêm trên trang",
        "operations": [],
        "contextRequests": [{"reason": "MISSING_RESOURCE_CONTEXT", "description": description, "question": question}],
    })


def plan_missing_target(instruction: str, context: AiPageContext) -> AiModificationPlan | None:
    """NEED_MORE_CONTEXT for a named section or table the Page lacks, else None."""
    command = Folded(command_text(instruction))
    completeness = context.completeness

    table = _named(TABLE, command)
    if table and not completeness.databases.truncated:
        names = [database.name for database in context.databases]
        if not any(_contains(name, table) or _contains(table, name) for name in names):
            return _ask(
                context, f'Trang không có bảng "{table}".{_listed(names, "Trang chưa có bảng nào.")}',
                "Bạn muốn thêm vào bảng nào?",
            )

    section = _named(SECTION, command)
    if section and not completeness.blocks.truncated and not completeness.textTruncated:
        texts: list[str] = []
        headings: list[str] = []
        for block in context.blocks:
            content: Any = block.content if isinstance(block.content, dict) else {}
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
                if block.type in ("HEADER", "TOGGLE"):
                    headings.append(text)
        # "thêm vào phần Việc tuần sau chuẩn bị slide, gửi lịch" (no ":"): the
        # words after a real heading's name are content, not part of the name.
        starts_with_heading = any(
            text_key(section).startswith(text_key(heading) + " ") for heading in headings if text_key(heading)
        )
        if not starts_with_heading and not any(_contains(text, section) for text in texts):
            return _ask(
                context, f'Trang không có phần "{section}".{_listed(headings, "Trang chưa có heading nào.")}',
                "Bạn muốn thêm vào phần nào?",
            )
    return None
