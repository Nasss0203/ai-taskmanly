"""Rows added to a named table without the model (kế hoạch sửa lỗi tạo trang và bảng, P6).

"thêm task Viết test API vào bảng Tasks", "add rows Smoke test, Rollback plan to
the Tasks table", "thêm sách X vào bảng Sách với tình trạng Đang đọc": the table
is named, the row titles are spelled out and a status, if any, is one option of
one SELECT column. Anything unsure — no such table, an unknown status, a title
ending in an option name ("… đang đọc" with no "tình trạng") — is left to the
model, which took ~16 s for each of these sentences.
"""

import re
from typing import Any

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    AiPageContext,
)
from app.modules.modification_planner.services.explicit_content import CLAUSE, INSERT, _command, _list_items
from app.modules.modification_planner.services.explicit_plan import plan_explicit_content
from app.modules.modification_planner.services.sentence_text import Folded, command_text, text_key
from app.modules.modification_planner.services.todo_status import PLAN_ADAPTER

DATABASE_ROWS_MODEL = "database-rows-v1"
ROWS_AND_BLOCKS_MODEL = "rows-and-blocks-v1"

VERB = r"(?:them|add|insert)"
ROW_WORD = r"(?:(?:mot|a|an|new)\s+)?(?:(?:cuon(?:\s+sach)?|tasks?|dong|hang|rows?|sach|books?|items?|muc|viec|cong viec)\s+)?"
STATUS_WORD = r"(?:trang thai|tinh trang|status)"
STATUS = rf"(?:,?\s+(?:voi\s+|with\s+)?{STATUS_WORD}\s+(?:la\s+|is\s+|:\s*)?(?P<{{name}}>[^,]+?))"
TABLE = r"\s+(?:vao|to|into|in)\s+(?:the\s+)?(?:bang\s+|table\s+)?(?P<table>.+?)(?:\s+table)?"

# Lazy and greedy names: "Deploy to staging to the Tasks table" holds two "to";
# the split whose table is a real table wins.
ROWS = tuple(re.compile(
    rf"^{VERB}\s+(?:(?P<count>\d+)\s+)?{ROW_WORD}(?P<names>.+{lazy}){STATUS.format(name='status1')}?"
    rf"{TABLE}{STATUS.format(name='status2')}?$"
) for lazy in ("?", ""))
QUOTE_CHARS = "\"'`“”‘’"
# "thêm 2 dòng vào bảng Tasks: A, B"
LISTED = re.compile(
    rf"^{VERB}\s+(?:(?P<count>\d+)\s+)?(?:dong|hang|rows?|tasks?|sach|books?)\s+(?:vao|to|into)\s+(?:the\s+)?"
    rf"(?:bang\s+)?(?P<table>[^:]+?)(?:\s+table)?\s*:\s*(?P<names>.+)$"
)


def _group(match: re.Match[str], folded: Folded, name: str) -> str | None:
    if match.group(name) is None:
        return None
    return folded.original(*match.span(name)).strip(" ,.")


def plan_database_rows(instruction: str, context: AiPageContext) -> AiModificationPlan | None:
    """A plan adding the named rows to the named table, or None to use the model."""
    if not context.databases:
        return None
    folded = Folded(command_text(instruction))
    database, match = None, None
    # Bước 3 (bỏ dấu hai chấm): "thêm 2 dòng vào bảng Tasks Viết test, Sửa lỗi":
    # the names follow a real table's name, with or without ":".
    for db in context.databases:
        after = re.compile(
            rf"^{VERB}\s+(?:(?P<count>\d+)\s+)?(?:dong|hang|rows?|tasks?|sach|books?)\s+(?:vao|to|into)\s+"
            rf"(?:the\s+)?(?:bang\s+)?(?P<table>{re.escape(text_key(db.name))})(?:\s+table)?\s*:?\s+(?P<names>.+)$"
        )
        found = after.match(" ".join(folded.value.split()))
        if found and " ".join(folded.value.split()) == folded.value:
            database, match = db, found
            break
    for pattern in (() if database else (LISTED, *ROWS)):
        found = pattern.match(folded.value)
        table = _group(found, folded, "table") if found else None
        same = [db for db in context.databases if table and text_key(db.name) == text_key(table)]
        if len(same) == 1:
            database, match = same[0], found
            break
    if database is None or match is None:
        return None
    titles = [prop for prop in database.properties if prop.type == "TITLE"]
    if len(titles) != 1:
        return None

    names = [name.strip(QUOTE_CHARS + " ") for name in _list_items(_group(match, folded, "names") or "") or []]
    if any(re.search(rf"\b{STATUS_WORD}\b", text_key(name)) for name in names):
        return None
    count = match.group("count")
    if not names or (count and int(count) != len(names)) or any(":" in name for name in names):
        return None
    selects = [prop for prop in database.properties if prop.type == "SELECT"]
    options = [(prop, option) for prop in selects for option in prop.options]
    status = _group(match, folded, "status1") if "status1" in match.groupdict() else None
    status = status or (_group(match, folded, "status2") if "status2" in match.groupdict() else None)
    # "Tuổi trẻ đáng giá bao nhiêu đang đọc": the last words may be a status.
    for index, name in enumerate(names):
        key = text_key(name)
        ending = [option for _, option in options
                  if key == text_key(option.name) or key.endswith(" " + text_key(option.name))]
        if not ending:
            continue
        size = len(text_key(ending[0].name).split())
        if status or len(names) != 1 or len(ending) != 1 or size < 2 or len(name.split()) <= size:
            return None
        names[index] = " ".join(name.split()[:-size])
        status = ending[0].name

    extra: dict[str, Any] = {}
    if status:
        found = [(prop, option) for prop, option in options if text_key(option.name) == text_key(status)]
        if len(found) != 1:
            return None
        prop, option = found[0]
        extra = {prop.id: option.id}

    return PLAN_ADAPTER.validate_python({
        "schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": context.page.id,
        "status": "PLAN_READY", "summary": instruction.strip(),
        "operations": [{
            "type": "CREATE_DATABASE_ROWS", "databaseId": database.id,
            "rows": [{"values": {titles[0].id: name[:1].upper() + name[1:], **extra}} for name in names],
        }],
    })


def _unhide(text: str, quoted: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda match: quoted[int(match.group(1))], text).strip(" ,.")


def plan_rows_and_blocks(instruction: str, context: AiPageContext) -> AiModificationPlan | None:
    """ "thêm dòng X vào bảng Y và heading Z": the rows, then the blocks, in one plan."""
    if not context.databases:
        return None
    text, quoted, _ = _command(instruction)
    verb = INSERT.match(text)
    if verb is None:
        return None
    for split in CLAUSE.finditer(text, verb.end()):
        if not re.match(r"\s+(?:và|va|and)\s", split.group(0), re.IGNORECASE):
            continue
        rows = plan_database_rows(_unhide(text[:split.start()], quoted), context)
        if rows is None:
            continue
        blocks = plan_explicit_content(verb.group(0) + _unhide(text[split.end():], quoted), context, None)
        if blocks is None:
            return None
        return PLAN_ADAPTER.validate_python({
            "schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": context.page.id,
            "status": "PLAN_READY", "summary": instruction.strip(),
            "operations": [operation.model_dump(mode="json")
                           for operation in (*rows.operations, *blocks.operations)],
        })
    return None
