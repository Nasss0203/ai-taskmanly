"""M8 (kế hoạch ngữ cảnh RAG, I5): a draft written from references keeps only
the items that come from a passage or from the user's own words.

The prompt already forbids invented items, but the 4B planner did not follow it
reliably: measured on ten sentences it copied a prompt example ("Chuẩn bị
release") and added tasks no passage held. This check is deterministic, so
"không bịa" holds whatever the model writes.
"""

import re
import unicodedata
from typing import Any

# Words most sentences share: "bị" in "bị crash" must not ground "chuẩn bị".
FILLER = frozenset(
    ["bi", "cac", "cho", "khi", "tren", "trong", "cua", "la", "de", "co", "khong", "duoc", "voi", "sau", "lai", "va", "mot", "nhung", "the", "and", "of", "to", "in", "on", "for", "a", "an"]
)
# Share of an item's words that must be found, in the request alone or in one
# passage (with the request); at least half must be the passage's own words.
REQUEST_SHARE = 0.6
PASSAGE_SHARE = 0.6
PASSAGE_OWN_SHARE = 0.5


def _words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFD", text)
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    folded = folded.replace("đ", "d").replace("Đ", "D").casefold()
    return [word for word in re.split(r"[^\w]+", folded) if len(word) > 1 and word not in FILLER]


def is_grounded(text: str, passages: list[str], instruction: str) -> bool:
    own = _words(text)
    if not own:
        return True

    def share(source: str) -> float:
        pool = set(_words(source))
        return sum(word in pool for word in own) / len(own)

    if share(instruction) >= REQUEST_SHARE:
        return True
    return any(
        share(f"{passage} {instruction}") >= PASSAGE_SHARE and share(passage) >= PASSAGE_OWN_SHARE
        for passage in passages
    )


def keep_grounded_blocks(
    operations: list[dict[str, Any]],
    passages: list[str],
    instruction: str,
) -> tuple[list[dict[str, Any]], int]:
    """INSERT_BLOCKS operations without ungrounded blocks, and how many were dropped.

    An operation left with no block is dropped too; other operations are kept.
    """
    kept: list[dict[str, Any]] = []
    dropped = 0
    for operation in operations:
        if operation.get("type") != "INSERT_BLOCKS":
            kept.append(operation)
            continue
        blocks = []
        for block in operation.get("blocks") or []:
            text = (block.get("content") or {}).get("text")
            if isinstance(text, str) and not is_grounded(text, passages, instruction):
                dropped += 1
                continue
            blocks.append(block)
        if blocks:
            kept.append({**operation, "blocks": blocks})
    return kept, dropped
