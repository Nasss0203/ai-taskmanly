"""Tick or untick existing to-dos without the model (kế hoạch tích to-do).

The user names to-dos in their own words ("đánh dấu gửi email là đã xong").
Each name is matched against the TODO blocks of the Page context: an exact
match first, then a whole-word part of exactly one to-do. Anything else is
asked back through NEED_MORE_CONTEXT / AMBIGUOUS_TARGET, never guessed.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    AiPageContext,
)
from app.modules.modification_planner.services.sentence_text import (
    PAGE_WORD,
    QUOTES,
    Folded,
    command_text,
    fold,
    text_key,
)

TODO_STATUS_PROVIDER = "rules"
TODO_STATUS_MODEL = "todo-status-v1"

PLAN_ADAPTER = TypeAdapter(AiModificationPlan)

# Shown when a name is not found; the rest is cut with "…".
LISTED_TODOS = 10
MIN_ITEM_LETTERS = 2

STATUS = r"(?:xong|hoan thanh|done|complete|completed)"
NOT_DONE = r"(?:chua xong|chua hoan thanh|not done|incomplete)"
ITEMS = r"(?P<items>.+?)"

# (checked, item names come first, pattern) — the first full match wins, so
# "bỏ tích" and "chưa xong" are tried before the shorter tick forms.
PATTERNS: tuple[tuple[bool, bool, re.Pattern[str]], ...] = tuple(
    (checked, item_first, re.compile(pattern))
    for checked, item_first, pattern in (
        (False, False, rf"(?:bo tich|bo danh dau|uncheck)\s+{ITEMS}"),
        (False, False, rf"(?:danh dau|mark)\s+{ITEMS}\s+(?:(?:la|as)\s+)?{NOT_DONE}"),
        (False, True, rf"{ITEMS}\s+{NOT_DONE}"),
        (True, False, rf"(?:danh dau|mark)\s+(?:(?:la|as)\s+)?(?:da\s+)?{STATUS}\s+{ITEMS}"),
        (True, False, rf"(?:danh dau|mark)\s+{ITEMS}\s+(?:(?:la|as)\s+)?(?:da\s+)?{STATUS}(?:\s+roi)?"),
        (True, False, rf"(?:hoan thanh|lam xong|complete|finish)\s+{ITEMS}"),
        # "tích hợp" (integrate) and "tích cực" are not ticks; "check list" is a list.
        (True, False, rf"(?:tich(?!\s+(?:hop|cuc)\b)|check(?!\s+list\b))\s+{ITEMS}"),
        (True, True, rf"{ITEMS}\s+(?:da\s+)?{STATUS}(?:\s+roi)?"),
    )
)

TRAILING_STATUS = re.compile(rf"(?:\s+(?:la|as))?(?:\s+da)?\s+{STATUS}(?:\s+roi)?$")
ITEM_SEPARATOR = re.compile(r"\s*(?:[,;]|\b(?:va|and)\b)\s*")
FILLER = re.compile(r"^(?:(?:phan|muc|viec|cong viec|to-do|todo|task)\s+)+")
INSERT_FIRST = re.compile(r"^(?:them|chen|bo sung|ghi them|add|insert|append|prepend)\b")


@dataclass(frozen=True)
class TodoItem:
    text: str
    key: str


@dataclass(frozen=True)
class TodoStatusRequest:
    checked: bool
    items: tuple[TodoItem, ...]
    # "gửi email xong rồi": only a tick when a name matches a to-do.
    item_first: bool


@dataclass(frozen=True)
class TodoCandidate:
    block_id: str
    text: str
    checked: bool
    key: str


def _items(text: str) -> tuple[TodoItem, ...]:
    folded = Folded(text)
    items: list[TodoItem] = []
    start = 0
    for separator in [*ITEM_SEPARATOR.finditer(folded.value), None]:
        end = separator.start() if separator else len(folded.value)
        piece = Folded(folded.original(start, end).strip(" " + QUOTES))
        filler = FILLER.match(piece.value)
        name = piece.original(filler.end() if filler else 0, len(piece.value)).strip(" " + QUOTES + ".!")
        if name:
            items.append(TodoItem(text=name, key=text_key(name)))
        if separator:
            start = separator.end()
    return tuple(items)


def parse_todo_status(instruction: str) -> TodoStatusRequest | None:
    """The tick / untick request in a sentence, or None if it is not one."""
    command = Folded(command_text(instruction))
    for checked, item_first, pattern in PATTERNS:
        match = pattern.fullmatch(command.value)
        if not match:
            continue
        span = command.original(*match.span("items"))
        names = Folded(span)
        status = TRAILING_STATUS.search(names.value)
        if status and not item_first:
            span = names.original(0, status.start())
        items = _items(span)
        # "hoàn thành trang sub man": a Page is never a to-do name.
        if not items or any(PAGE_WORD.search(item.key) for item in items):
            return None
        return TodoStatusRequest(checked, items, item_first)
    return None


def todos_in(context: AiPageContext) -> list[TodoCandidate]:
    todos = []
    for block in context.blocks:
        content = block.content if isinstance(block.content, dict) else {}
        text = content.get("text")
        if block.type == "TODO" and isinstance(text, str) and text.strip():
            todos.append(TodoCandidate(block.id, text, content.get("checked") is True, text_key(text)))
    return todos


def match_item(item: TodoItem, todos: list[TodoCandidate], checked: bool) -> list[TodoCandidate]:
    """Exact names first, then a whole-word part of the name.

    Among same-named to-dos the one that would change is meant; a part of
    several different names is always asked back, never narrowed down.
    """
    if len(item.key.replace(" ", "")) < MIN_ITEM_LETTERS:
        return []
    exact = [todo for todo in todos if todo.key == item.key]
    if exact:
        return [todo for todo in exact if todo.checked != checked] or exact
    return [todo for todo in todos if f" {item.key} " in f" {todo.key} "]


def _quoted(names: list[str]) -> str:
    return ", ".join(f'"{name}"' for name in names)


def _ask(description: str, question: str) -> dict[str, Any]:
    return {"reason": "AMBIGUOUS_TARGET", "description": description, "question": question}


def plan_todo_status(instruction: str, context: AiPageContext) -> AiModificationPlan | None:
    """A plan for a tick / untick request, or None to use the normal planner."""
    request = parse_todo_status(instruction)
    if request is None:
        return None
    todos = todos_in(context)
    matches = [(item, match_item(item, todos, request.checked)) for item in request.items]
    # "thêm mục Hoàn thành xong rồi" is an insert when no to-do matches; any
    # other names-first sentence is asked back, never sent to the insert model.
    if (request.item_first and not any(found for _, found in matches)
            and INSERT_FIRST.match(request.items[0].key)):
        return None

    verb = "tích" if request.checked else "bỏ tích"
    asks: list[dict[str, Any]] = []
    chosen: dict[str, tuple[TodoItem, TodoCandidate]] = {}
    for item, found in matches:
        if not found:
            names = [todo.text for todo in todos]
            listed = (
                f" Các to-do đang có: {', '.join(names[:LISTED_TODOS])}{'…' if len(names) > LISTED_TODOS else ''}."
                if names else " Trang chưa có to-do nào."
            )
            truncated = " Trang dài nên AI chỉ đọc được một phần." if context.completeness.blocks.truncated else ""
            asks.append(_ask(
                f'Không thấy to-do "{item.text}" trên trang.{listed}{truncated}',
                f"Bạn muốn {verb} to-do nào?",
            ))
        elif len(found) > 1:
            same_name = len({todo.key for todo in found}) == 1
            asks.append(_ask(
                f'Có {len(found)} to-do "{found[0].text}".' if same_name
                else f'"{item.text}" khớp nhiều to-do: {", ".join(todo.text for todo in found)}.',
                f"Bạn có thể đổi tên một to-do hoặc {verb} trực tiếp trên trang." if same_name
                else f"Hãy ghi rõ tên to-do bạn muốn {verb}.",
            ))
        elif found[0].block_id in chosen:
            first, todo = chosen[found[0].block_id]
            asks.append(_ask(
                f'"{first.text}" và "{item.text}" cùng chỉ to-do "{todo.text}".',
                f"Hãy ghi rõ từng to-do bạn muốn {verb}.",
            ))
        else:
            chosen[found[0].block_id] = (item, found[0])

    picked = [todo for _, todo in chosen.values()]
    changes = [todo for todo in picked if todo.checked != request.checked]
    unchanged = [todo.text for todo in picked if todo.checked == request.checked]
    state = "đã được tích rồi" if request.checked else "đang chưa được tích"
    if not asks and not changes:
        asks.append(_ask(f"{_quoted(unchanged)} {state}.", f"Bạn muốn {verb} to-do nào khác?"))

    plan: dict[str, Any] = {"schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": context.page.id}
    if asks:
        plan |= {
            "status": "NEED_MORE_CONTEXT",
            "summary": f"Cần làm rõ to-do cần {verb}",
            "operations": [],
            "contextRequests": asks,
        }
    else:
        skipped = f" (bỏ qua {_quoted(unchanged)} vì {state})" if unchanged else ""
        plan |= {
            "status": "PLAN_READY",
            "summary": f"{verb.capitalize()} {len(changes)} to-do: {', '.join(todo.text for todo in changes)}{skipped}",
            "operations": [
                {"type": "SET_TODO_CHECKED", "blockId": todo.block_id, "text": todo.text, "checked": request.checked}
                for todo in changes
            ],
        }
    return PLAN_ADAPTER.validate_python(plan)
