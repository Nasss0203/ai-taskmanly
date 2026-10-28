"""Delete existing blocks without the model (kế hoạch xoá block, bước 3).

"xoá to-do gửi email": each named block is chosen like a text edit (an exact
text, else a whole-word part of exactly one block). A toggle goes with its
nested blocks, which the draft lists. Anything unsure is asked back, and a
sentence is never half-deleted.
"""

import re
from typing import Any

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    AiPageContext,
    AiPageContextBlock,
)
from app.modules.modification_planner.services.block_text import (
    TextBlock,
    match_exact,
    match_partial,
    text_blocks,
)
from app.modules.modification_planner.services.sentence_text import (
    PAGE_WORD,
    QUOTES,
    Folded,
    command_text,
    text_key,
)
from app.modules.modification_planner.services.todo_status import ITEM_SEPARATOR, PLAN_ADAPTER

MAX_DELETES = 10
LISTED_BLOCKS = 10

# "bỏ tích" (untick), "bỏ qua" (override) and "bổ sung" (add) are not deletes.
VERB = re.compile(
    r"^(?:xoa(?:\s+bo)?|bo(?!\s+(?:tich|danh dau|qua|sung)\b)|go(?:\s+bo)?|delete|remove)\s+",
)
# "xoá hết / tất cả …" is a bulk delete; never one of the named blocks.
BULK = re.compile(r"^(?:het|tat ca|moi|toan bo|all|everything)\b")
STRIP = " " + QUOTES + ".!,"


def parse_block_delete(instruction: str) -> tuple[str, ...] | None:
    """The block names a sentence deletes, or None if it is not a delete."""
    command = Folded(command_text(instruction))
    verb = VERB.match(command.value)
    if not verb:
        return None
    rest = Folded(command.original(verb.end(), len(command.value)))
    names: list[str] = []
    start = 0
    for separator in [*ITEM_SEPARATOR.finditer(rest.value), None]:
        end = separator.start() if separator else len(rest.value)
        name = rest.original(start, end).strip(STRIP)
        if name:
            names.append(name)
        if separator:
            start = separator.end()
    # "xoá trang X", "xoá nội dung trang", "xoá hết": a whole Page or a bulk delete.
    if not names or any(PAGE_WORD.search(text_key(name)) or BULK.match(text_key(name)) for name in names):
        return None
    return tuple(names)


def descendants(block_id: str, context: AiPageContext) -> list[AiPageContextBlock]:
    """Every block nested under ``block_id``, in page order."""
    children: dict[str, list[AiPageContextBlock]] = {}
    for block in sorted(context.blocks, key=lambda item: item.orderIndex):
        if block.parentBlockId:
            children.setdefault(block.parentBlockId, []).append(block)
    found: list[AiPageContextBlock] = []
    pending = [block_id]
    while pending:
        for child in children.get(pending.pop(0), []):
            found.append(child)
            pending.append(child.id)
    return found


def _ask(description: str, question: str) -> dict[str, Any]:
    return {"reason": "AMBIGUOUS_TARGET", "description": description, "question": question}


def plan_block_delete(instruction: str, context: AiPageContext) -> AiModificationPlan | None:
    """A plan for "xoá X, Y", or None to use the normal planner."""
    names = parse_block_delete(instruction)
    if names is None:
        return None
    blocks = text_blocks(context)
    asks: list[dict[str, Any]] = []
    chosen: dict[str, tuple[str, TextBlock]] = {}

    if len(names) > MAX_DELETES:
        asks.append(_ask(f"Mỗi lần chỉ xoá được tối đa {MAX_DELETES} block.", "Hãy chia thành nhiều yêu cầu."))
    for name in names if not asks else ():
        match = match_exact(name, blocks) or match_partial(name, blocks)
        if match is None:
            texts = [block.text for block in blocks]
            listed = (
                f" Các block đang có: {', '.join(texts[:LISTED_BLOCKS])}{'…' if len(texts) > LISTED_BLOCKS else ''}."
                if texts else " Trang chưa có block chữ nào."
            )
            truncated = " Trang dài nên AI chỉ đọc được một phần." if context.completeness.blocks.truncated else ""
            asks.append(_ask(f'Không thấy "{name}" trên trang.{listed}{truncated}', "Bạn muốn xoá block nào?"))
        elif len(match.blocks) > 1:
            same_text = len({block.key for block in match.blocks}) == 1
            asks.append(_ask(
                f'Có {len(match.blocks)} block "{match.blocks[0].text}".' if same_text
                else f'"{name}" có trong nhiều block: {", ".join(block.text for block in match.blocks)}.',
                "Hãy ghi rõ hơn block cần xoá, hoặc xoá trực tiếp trên trang.",
            ))
        elif match.blocks[0].block_id in chosen:
            first, block = chosen[match.blocks[0].block_id]
            asks.append(_ask(
                f'"{first}" và "{name}" cùng chỉ block "{block.text}".', "Hãy ghi rõ từng block cần xoá.",
            ))
        else:
            chosen[match.blocks[0].block_id] = (name, match.blocks[0])

    # A block nested in another deleted block goes with it; no second operation.
    nested = {child.id for block_id in chosen for child in descendants(block_id, context)}
    deletes = [block for block_id, (_, block) in chosen.items() if block_id not in nested]
    by_id = {block.id: block for block in context.blocks}
    if not asks and context.completeness.blocks.truncated:
        for block in deletes:
            if by_id[block.block_id].type == "TOGGLE":
                asks.append(_ask(
                    f'Trang dài nên AI không đếm đủ block con của "{block.text}".',
                    "Hãy xoá toggle này trực tiếp trên trang.",
                ))

    plan: dict[str, Any] = {"schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": context.page.id}
    if asks:
        return PLAN_ADAPTER.validate_python(plan | {
            "status": "NEED_MORE_CONTEXT",
            "summary": "Cần làm rõ block cần xoá",
            "operations": [],
            "contextRequests": asks,
        })
    operations = [
        {"type": "DELETE_BLOCK", "blockId": block.block_id, "text": block.text,
         "childCount": len(descendants(block.block_id, context))}
        for block in deletes
    ]
    nested_total = sum(operation["childCount"] for operation in operations)
    summary = f"Xoá {len(operations)} block: " + ", ".join(f'"{block.text}"' for block in deletes)
    if nested_total:
        summary += f" (kèm {nested_total} block con)"
    return PLAN_ADAPTER.validate_python(plan | {
        "status": "PLAN_READY", "summary": summary, "operations": operations,
    })
