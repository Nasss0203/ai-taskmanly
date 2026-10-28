"""Deterministic clean-up of block structure and task lists in a draft.

Small models list tasks as numbered TOGGLE blocks even when the prompt asks
for TODO blocks. A childless TOGGLE cannot be expanded, so it only renders as
a plain line; a task-like one is turned into an unchecked TODO instead.
"""

import re

from app.modules.page_composition.schemas.page_composition_schema import (
    PageCompositionDraft,
)
from app.shared.list_markers import has_list_marker, strip_list_marker


TOGGLE_REQUEST = re.compile(
    r"toggle|gập|thu gọn|mở rộng|đóng mở|collaps", re.IGNORECASE,
)
TASK_REQUEST = re.compile(
    r"việc|nhiệm vụ|công việc|checklist|check list|todo|to-do|task|cần làm",
    re.IGNORECASE,
)


def normalize_task_blocks(
    draft: PageCompositionDraft, instruction: str,
) -> PageCompositionDraft:
    data = draft.model_dump()
    types = {block["ref"]: block["type"] for block in data["blocks"]}
    # The heading each block sits under: the HEADER the model nested it in, or
    # else the last HEADER before it ("Các nhiệm vụ cần hoàn thành:").
    texts = {block["ref"]: (block.get("content") or {}).get("text", "") for block in data["blocks"]}
    section: dict[str, str] = {}
    heading = ""
    for block in data["blocks"]:
        if block["type"] == "HEADER":
            heading = texts[block["ref"]]
        parent = block.get("parentRef")
        section[block["ref"]] = texts[parent] if types.get(parent) == "HEADER" else heading
    changed = False
    # Only a TOGGLE can hold children (NestJS rejects anything else). Models
    # often nest items "under" a HEADER: keep them, in order, at root level.
    for block in data["blocks"]:
        if block.get("parentRef") and types.get(block["parentRef"]) != "TOGGLE":
            block["parentRef"] = None
            changed = True
    # An explicit toggle request is honoured as generated.
    if TOGGLE_REQUEST.search(instruction):
        return PageCompositionDraft.model_validate(data) if changed else draft
    task_request = bool(TASK_REQUEST.search(instruction))
    parents = {block.get("parentRef") for block in data["blocks"]}
    for block in data["blocks"]:
        if block["type"] == "TOGGLE" and block["ref"] not in parents:
            text = block["content"]["text"]
            # Without a task request, only list-like lines or lines under a task
            # heading are tasks (keeps FAQs).
            if not (task_request or has_list_marker(text)
                    or TASK_REQUEST.search(section[block["ref"]])):
                continue
            block["type"] = "TODO"
            block["content"] = {"text": strip_list_marker(text), "checked": False}
            changed = True
        elif block["type"] == "TODO" and has_list_marker(block["content"]["text"]):
            block["content"]["text"] = strip_list_marker(block["content"]["text"])
            changed = True
    return PageCompositionDraft.model_validate(data) if changed else draft
