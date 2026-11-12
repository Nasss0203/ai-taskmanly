import re
from dataclasses import dataclass, field
from typing import Any

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiPageContext,
    AiPageContextDatabase,
    AiPageContextDatabaseProperty,
)
from app.modules.modification_planner.services.sentence_text import text_key
from app.shared.vi_vocabulary import pattern

MAX_LISTED = 10
VALUE_TYPES = {"SELECT", "STATUS", "MULTI_SELECT"}
UNFINISHED = re.compile(
    r"\b(?:chua|con lai|con gi|con viec|con nhung|con muc|con to ?do|not done|not finished|unfinished|"
    r"left|pending|open|remaining)\b"
)
FINISHED = re.compile(r"\b(?:da xong|da lam xong|da hoan thanh|da tich|xong roi|completed|finished|done)\b")
ASKED_VALUE = re.compile(
    r"\b(?:bao nhieu|how many)\s+(?:viec|dong|hang|task|tasks|row|rows|muc|ban ghi|records?|items?|cong viec)\s+"
    r"(?:(?:are|is|o trang thai|co trang thai|trang thai|dang o|dang|la)\s+)?(?P<value>.+?)"
    r"(?:\s+(?:trong|o|in|of|tai|cua)\b.*)?$"
)
POLITE_TAIL = re.compile(rf"(?:\s+{pattern('tail', 'trailing_with', 'trailing_go')})+$")
NOT_A_VALUE = re.compile(r"^(?:(?:trong|o|in|of|co|the|tat ca|all)\b|bang\b|table\b)")


@dataclass
class TodoFacts:
    done: list[str] = field(default_factory=list)
    open: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.done) + len(self.open)


def todo_facts(context: AiPageContext) -> TodoFacts:
    facts = TodoFacts()
    for block in context.blocks:
        content = block.content if isinstance(block.content, dict) else {}
        text = content.get("text")
        if block.type != "TODO" or not isinstance(text, str) or not text.strip():
            continue
        (facts.done if content.get("checked") is True else facts.open).append(text.strip())
    return facts


def _listed(items: list[str]) -> str:
    lines = [f"- {item}" for item in items[:MAX_LISTED]]
    if len(items) > MAX_LISTED:
        lines.append(f"và {len(items) - MAX_LISTED} mục khác")
    return "\n".join(lines)


def blocks_note(context: AiPageContext) -> str:
    blocks = context.completeness.blocks
    if not blocks.truncated:
        return ""
    return (f"\n(AI chỉ đọc được {blocks.included}/{blocks.total} block đầu của trang; "
            "số trên chỉ tính phần đã đọc.)")


def todo_answer(context: AiPageContext, question: str) -> tuple[str, dict[str, Any]]:
    facts = todo_facts(context)
    title = context.page.title or "này"
    data = {"todoTotal": facts.total, "todoDone": len(facts.done), "todoOpen": len(facts.open)}
    if not facts.total:
        return f'Trang "{title}" không có to-do nào.' + blocks_note(context), data
    key = text_key(question)
    asks_done = bool(FINISHED.search(key)) and not UNFINISHED.search(key)
    if asks_done:
        head = f'Trang "{title}" có {len(facts.done)}/{facts.total} việc đã xong'
        body = _listed(facts.done)
    elif facts.open:
        head = f'Trang "{title}" còn {len(facts.open)} việc chưa xong (đã xong {len(facts.done)}/{facts.total})'
        body = _listed(facts.open)
    else:
        return f'Trang "{title}" đã xong cả {facts.total} việc.' + blocks_note(context), data
    return (f"{head}:\n{body}" if body else f"{head}.") + blocks_note(context), data


def _named_in(name: str, key: str) -> bool:
    name_key = text_key(name)
    return bool(name_key) and re.search(rf"(?<!\w){re.escape(name_key)}(?!\w)", key) is not None


def find_database(
    context: AiPageContext, question: str, reference: str | None,
) -> AiPageContextDatabase | None:
    databases = context.databases
    if reference:
        wanted = text_key(reference)
        exact = [database for database in databases if text_key(database.name) == wanted]
        if exact:
            return exact[0]
        if len(databases) == 1 and text_key(context.page.title) == wanted:
            return databases[0]
        longer =[database for database in databases
                  if text_key(database.name) and wanted.startswith(text_key(database.name) + " ")]
        return longer[0] if len(longer) == 1 else None
    key = text_key(question)
    named = [database for database in databases if _named_in(database.name, key)]
    if named:
        return max(named, key=lambda database: len(database.name))
    return databases[0] if len(databases) == 1 else None


def _option_matches(
    database: AiPageContextDatabase, wanted: str,
) -> list[tuple[AiPageContextDatabaseProperty, str, str]]:
    found = []
    for prop in database.properties:
        if prop.type in VALUE_TYPES:
            found += [(prop, option.id, option.name) for option in prop.options if text_key(option.name) == wanted]
    return found


def _has_value(value: Any, option_id: str, option_name: str) -> bool:
    names = {option_id, option_name}
    if isinstance(value, list):
        return any(item in names for item in value)
    return value in names


def database_answer(
    context: AiPageContext, question: str, reference: str | None,
) -> tuple[str, dict[str, Any]]:
    title = context.page.title or "này"
    database = find_database(context, question, reference)
    if database is None:
        names = [database.name for database in context.databases][:5]
        asked = f' "{reference}"' if reference else ""
        if not names:
            return f'Trang "{title}" không có bảng{asked} nào.', {"databaseFound": False}
        return (f'Trang "{title}" không có bảng{asked}. Các bảng có trên trang: '
                + ", ".join(f'"{name}"' for name in names) + "."), {"databaseFound": False}
    rows = database.rows
    completeness = next((info for info in context.completeness.rows if info.databaseId == database.id), None)
    total = completeness.total if completeness else len(rows)
    note = (f" (AI chỉ đọc được {len(rows)}/{total} dòng; số trên chỉ tính phần đã đọc.)"
            if completeness and completeness.truncated else "")
    data: dict[str, Any] = {"databaseFound": True, "database": database.name, "rowTotal": total}
    asked = ASKED_VALUE.search(POLITE_TAIL.sub("", text_key(question)))
    value = asked.group("value").strip() if asked else ""
    if not value or NOT_A_VALUE.match(value) or _named_in(database.name, value):
        data["rowCount"] = total
        return f'Bảng "{database.name}" có {total} dòng.', data
    matches = _option_matches(database, value)
    if not matches:
        options = [option.name for prop in database.properties if prop.type in VALUE_TYPES for option in prop.options]
        known = (" Các giá trị có trong bảng: " + ", ".join(f'"{name}"' for name in options[:10]) + ".") if options else ""
        data["rowCount"] = None
        return f'Bảng "{database.name}" không có giá trị "{asked.group("value")}".{known}', data
    prop, option_id, option_name = matches[0]
    count = sum(1 for row in rows if _has_value(row.values.get(prop.id), option_id, option_name))
    data["rowCount"] = count
    return (f'Bảng "{database.name}" có {count} dòng {prop.name} = {option_name} '
            f"(trên tổng {total} dòng).{note}"), data


def known_numbers(context: AiPageContext) -> set[str]:
    found: set[str] = set()
    dump = context.model_dump(mode="json")
    for block in dump.get("blocks") or []:
        found |= set(re.findall(r"\d+", str(block.get("content") or "")))
    for database in dump.get("databases") or []:
        found |= set(re.findall(r"\d+", database.get("name") or ""))
        for row in database.get("rows") or []:
            found |= set(re.findall(r"\d+", str(row.get("values") or {})))
        found.add(str(len(database.get("rows") or [])))
    found |= set(re.findall(r"\d+", context.page.title or ""))
    todos = todo_facts(context)
    found |= {str(todos.total), str(len(todos.done)), str(len(todos.open))}
    for info in context.completeness.rows:
        found.add(str(info.total))
    found.add(str(context.completeness.blocks.total))
    return found
