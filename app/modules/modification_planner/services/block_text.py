"""Change the text of one existing block without the model (kế hoạch sửa chữ block).

"đổi X thành Y": X is matched against the text blocks of the Page context.
X equal to one block's text replaces that text; X found once, as whole words,
in exactly one block replaces only that part. Anything else is asked back.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    AiPageContext,
)
from app.modules.modification_planner.services.sentence_text import (
    PAGE_WORD,
    QUOTES,
    Folded,
    command_text,
    text_key,
)
from app.modules.modification_planner.services.todo_status import PLAN_ADAPTER

EDITABLE_TYPES = ("TEXT", "HEADER", "QUOTE", "TODO", "TOGGLE")
MAX_TEXT_LENGTH = 2000
LISTED_BLOCKS = 10
MIN_NAME_LETTERS = 2

VERB = re.compile(
    r"^(?:chinh sua|thay doi|doi|sua|thay|chinh|cap nhat|change|update|edit|replace|rename)\s+",
)
INTO = re.compile(r"\s+(?:thanh|sang|bang|to|with|into)\s+")
# Words that only say which block ("đổi to-do X", "sửa heading X"). They may
# also start a real text ("Việc tuần sau"), so names are tried with and without.
FILLER_WORD = re.compile(
    r"^(?:ten|noi dung|chu|cua|phan|muc|viec|cong viec|to-do|todo|task|heading|tieu de|"
    r"block|dong|doan|cau|the|text|title|toggle)\s+",
)
STRIP = " " + QUOTES + ".!,"


@dataclass(frozen=True)
class TextBlock:
    block_id: str
    text: str
    key: str


@dataclass(frozen=True)
class BlockTextRequest:
    # Every way to split the sentence at "thành / to …": (old, new).
    splits: tuple[tuple[str, str], ...]


def _names(old: str) -> list[str]:
    """The typed name with 0, 1, 2… leading filler words removed."""
    names = [old]
    folded = Folded(old)
    start = 0
    while filler := FILLER_WORD.match(folded.value[start:]):
        start += filler.end()
        name = folded.original(start, len(folded.value)).strip(STRIP)
        if name:
            names.append(name)
    return names


def parse_block_text(instruction: str) -> BlockTextRequest | None:
    """The block text change in a sentence, or None if it is not one."""
    command = Folded(command_text(instruction))
    verb = VERB.match(command.value)
    if not verb:
        return None
    splits = []
    for into in INTO.finditer(command.value, verb.end()):
        old = command.original(verb.end(), into.start()).strip(STRIP)
        new = command.original(into.end(), len(command.value)).strip(STRIP)
        # "đổi tên trang X thành Y" renames a Page; it never edits a block.
        if old and new and not PAGE_WORD.search(text_key(old)):
            splits.append((old, new))
    return BlockTextRequest(tuple(splits)) if splits else None


def text_blocks(context: AiPageContext) -> list[TextBlock]:
    blocks = []
    for block in context.blocks:
        content = block.content if isinstance(block.content, dict) else {}
        text = content.get("text")
        if block.type in EDITABLE_TYPES and isinstance(text, str) and text.strip():
            blocks.append(TextBlock(block.id, text, text_key(text)))
    return blocks


def _occurrences(name: str, block: TextBlock) -> list[tuple[int, int]]:
    """Whole-word places of ``name`` in the block's original text."""
    words = text_key(name).split()
    if not words:
        return []
    folded = Folded(block.text)
    pattern = r"(?<![^\W_])" + r"[\W_]+".join(map(re.escape, words)) + r"(?![^\W_])"
    return [folded.span(*match.span()) for match in re.finditer(pattern, folded.value)]


@dataclass(frozen=True)
class BlockMatch:
    blocks: tuple[TextBlock, ...]
    # The original span to replace; None replaces the whole text.
    span: tuple[int, int] | None = None
    repeated: int = 0


def _names_of(old: str) -> list[str]:
    return [name for name in _names(old) if len(text_key(name).replace(" ", "")) >= MIN_NAME_LETTERS]


def match_exact(old: str, blocks: list[TextBlock]) -> BlockMatch | None:
    for name in _names_of(old):
        exact = tuple(block for block in blocks if block.key == text_key(name))
        if exact:
            return BlockMatch(exact)
    return None


def match_partial(old: str, blocks: list[TextBlock]) -> BlockMatch | None:
    for name in _names_of(old):
        found = [(block, _occurrences(name, block)) for block in blocks]
        found = [(block, places) for block, places in found if places]
        if len(found) > 1:
            return BlockMatch(tuple(block for block, _ in found))
        if found:
            block, places = found[0]
            return BlockMatch((block,), places[0], len(places) if len(places) > 1 else 0)
    return None


def _ask(description: str, question: str) -> dict[str, Any]:
    return {"reason": "AMBIGUOUS_TARGET", "description": description, "question": question}


def plan_block_text(instruction: str, context: AiPageContext) -> AiModificationPlan | None:
    """A plan for "đổi X thành Y", or None to use the normal planner."""
    request = parse_block_text(instruction)
    if request is None:
        return None
    blocks = text_blocks(context)
    old, new = request.splits[0]
    match = None
    # An exact block name at any split beats a part found at an earlier one.
    for find in (match_exact, match_partial):
        for split in request.splits:
            match = find(split[0], blocks)
            if match:
                old, new = split
                break
        if match:
            break

    ask = None
    if match is None:
        names = [block.text for block in blocks]
        listed = (
            f" Các block đang có: {', '.join(names[:LISTED_BLOCKS])}{'…' if len(names) > LISTED_BLOCKS else ''}."
            if names else " Trang chưa có block chữ nào."
        )
        truncated = " Trang dài nên AI chỉ đọc được một phần." if context.completeness.blocks.truncated else ""
        ask = _ask(f'Không thấy "{old}" trên trang.{listed}{truncated}', "Bạn muốn sửa block nào?")
    elif len(match.blocks) > 1:
        same_text = len({block.key for block in match.blocks}) == 1
        ask = _ask(
            f'Có {len(match.blocks)} block "{match.blocks[0].text}".' if same_text
            else f'"{old}" có trong nhiều block: {", ".join(block.text for block in match.blocks)}.',
            "Hãy ghi rõ hơn chữ cần sửa, hoặc sửa trực tiếp trên trang.",
        )
    elif match.repeated:
        ask = _ask(
            f'"{old}" xuất hiện {match.repeated} lần trong "{match.blocks[0].text}".',
            "Hãy ghi cả câu cần sửa.",
        )

    if ask is None:
        block = match.blocks[0]
        if match.span is None:
            new_text = new
        else:
            start, end = match.span
            new_text = block.text[:start] + new + block.text[end:]
        if new_text == block.text:
            ask = _ask(f'"{block.text}" đã như vậy rồi.', "Bạn muốn sửa gì khác?")
        elif len(new_text) > MAX_TEXT_LENGTH:
            ask = _ask(f"Chữ mới dài quá {MAX_TEXT_LENGTH} ký tự.", "Hãy rút ngắn chữ mới.")

    plan: dict[str, Any] = {"schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": context.page.id}
    if ask is not None:
        plan |= {
            "status": "NEED_MORE_CONTEXT",
            "summary": "Cần làm rõ block cần sửa",
            "operations": [],
            "contextRequests": [ask],
        }
    else:
        plan |= {
            "status": "PLAN_READY",
            "summary": f'Sửa 1 block: "{block.text}" → "{new_text}"',
            "operations": [
                {"type": "SET_BLOCK_TEXT", "blockId": block.block_id, "oldText": block.text, "newText": new_text},
            ],
        }
    return PLAN_ADAPTER.validate_python(plan)
