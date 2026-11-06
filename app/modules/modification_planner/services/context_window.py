"""What of the Page context goes into the planner prompt (kế hoạch trang dài, E3/E4).

The prompt gets the compact context (D.2: no metadata, block ids and databases
exact). A Page over the token budget sends only the part the sentence needs:
the outline (every root HEADER / TOGGLE), the section the sentence names, the
blocks it names, and the last root blocks (where a sentence naming no place
goes). Validators and rules always read the full context.
"""

import json
from typing import Any

from app.modules.modification_planner.schemas.modification_planner_schema import AiPageContext
from app.modules.modification_planner.services.sentence_text import text_key

TAIL_BLOCKS = 10
# Tokens per character of the compact JSON, measured on Vietnamese pages (E2).
CHARS_PER_TOKEN = 2.5  # measured 2.57 (E2), rounded down


def estimate_tokens(value: Any) -> int:
    return int(len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) / CHARS_PER_TOKEN) + 1


def compact_context(context: AiPageContext) -> dict[str, Any]:
    data = context.model_dump(mode="json", exclude_unset=True)
    compact: dict[str, Any] = {
        "page": {"id": data["page"]["id"], "title": data["page"].get("title")},
        "blocks": [
            {key: value for key, value in block.items() if value is not None or key == "parentBlockId"}
            for block in data.get("blocks") or []
        ],
    }
    if data.get("databaseReferences"):
        compact["databaseReferences"] = data["databaseReferences"]
    if data.get("databases"):
        # Kept whole: without "views" the model lost the TITLE column (gp28, gp30).
        compact["databases"] = data["databases"]
    completeness = data.get("completeness") or {}
    cut = (
        completeness.get("textTruncated")
        or (completeness.get("blocks") or {}).get("truncated")
        or (completeness.get("databases") or {}).get("truncated")
        or any(row.get("truncated") for row in completeness.get("rows") or [])
    )
    if cut:
        compact["completeness"] = completeness
    return compact


def _named(text: str, sentence: str) -> bool:
    key = text_key(text)
    return bool(key) and f" {key} " in f" {sentence} "


def window_context(context: AiPageContext, instruction: str, budget_tokens: int) -> dict[str, Any]:
    full = compact_context(context)
    if estimate_tokens(full) <= budget_tokens:
        return full

    sentence = text_key(instruction)
    blocks = context.blocks
    children: dict[str, list[str]] = {}
    for block in blocks:
        if block.parentBlockId:
            children.setdefault(block.parentBlockId, []).append(block.id)

    def with_descendants(block_id: str) -> set[str]:
        found, pending = {block_id}, [block_id]
        while pending:
            for child in children.get(pending.pop(), []):
                found.add(child)
                pending.append(child)
        return found

    roots = [block for block in blocks if block.parentBlockId is None]
    keep: set[str] = set()
    # 1. Outline.
    keep |= {block.id for block in roots if block.type in ("HEADER", "TOGGLE")}
    # 2. The section the sentence names, to the next root HEADER.
    for index, block in enumerate(roots):
        text = (block.content or {}).get("text") if isinstance(block.content, dict) else None
        if block.type in ("HEADER", "TOGGLE") and isinstance(text, str) and _named(text, sentence):
            for member in roots[index:]:
                if member is not block and member.type == "HEADER":
                    break
                keep |= with_descendants(member.id)
    # 3. Blocks the sentence names (2+ words), with the toggle holding them.
    for block in blocks:
        text = (block.content or {}).get("text") if isinstance(block.content, dict) else None
        if isinstance(text, str) and len(text_key(text).split()) >= 2 and _named(text, sentence):
            keep.add(block.id)
            if block.parentBlockId:
                keep.add(block.parentBlockId)
    completeness = context.model_dump(mode="json", exclude_unset=True).get("completeness") or {}

    outline = {block.id for block in roots if block.type in ("HEADER", "TOGGLE")}

    def build(tail: int, row_cap: int | None, lite_outline: bool = False) -> dict[str, Any]:
        # 4. The end of the Page.
        kept = set(keep)
        for block in roots[-tail:]:
            kept |= with_descendants(block.id)
        detailed = kept - outline | (keep - outline) | {b.id for b in roots[-tail:]}
        window = dict(full)
        window["blocks"] = [
            # An outline-only heading needs its id, kind and text, nothing more.
            {key: block[key] for key in ("id", "type", "content") if key in block}
            if lite_outline and block["id"] in outline and block["id"] not in detailed else block
            for block in full["blocks"] if block["id"] in kept
        ]
        rows_info = [dict(row) for row in completeness.get("rows") or []]
        if row_cap is not None and full.get("databases"):
            databases = []
            for database in full["databases"]:
                rows = database.get("rows") or []
                databases.append({**database, "rows": rows[:row_cap]})
                for info in rows_info:
                    if info.get("databaseId") == database.get("id") and len(rows) > row_cap:
                        info.update(included=row_cap, truncated=True)
            window["databases"] = databases
        blocks_info = dict(completeness.get("blocks") or {})
        blocks_info.update(truncated=True, included=len(window["blocks"]))
        window["completeness"] = {**completeness, "blocks": blocks_info,
                                  **({"rows": rows_info} if rows_info else {})}
        return window

    # Shrink the tail, then the table rows, until the window fits; the outline
    # and the blocks the sentence names always stay.
    window: dict[str, Any] = {}
    for tail in (TAIL_BLOCKS, 6, 3):
        for row_cap in (None, 10, 5):
            window = build(tail, row_cap)
            if estimate_tokens(window) <= budget_tokens:
                return window
    for lite_outline in (False, True):
        window = build(3, 0, lite_outline)
        if estimate_tokens(window) <= budget_tokens:
            return window
    return window
