"""Drafts the sentence fully spells out, without the model (kế hoạch bỏ qua model, F1).

"thêm checklist gồm in tài liệu, đặt phòng" names every block and no place: the
content is read by rule (explicit_content.py) and a sentence naming no place goes
after the last root block (kế hoạch vị trí mặc định). The model added nothing
here but time (3–7 s) and the risk of following words inside the content.
Anything unsure — content, a named place, a source Page — is left to the model.
"""

import re
from typing import Any

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    AiPageContext,
)
from app.modules.modification_planner.services.explicit_content import (
    POSITION,
    _command,
    parse_explicit_blocks,
)
from app.modules.modification_planner.services.block_text import match_exact, match_partial, text_blocks
from app.modules.modification_planner.services.sentence_normalize import normalize_instruction
from app.modules.modification_planner.services.sentence_text import Folded, fold, text_key
from app.modules.modification_planner.services.todo_status import PLAN_ADAPTER
from app.shared.list_markers import strip_list_marker

EXPLICIT_CONTENT_MODEL = "explicit-content-v1"
# F2: "vào phần X", "sau dòng X", "under the X section", "after X" at the end of the sentence.
PLACE_VI = re.compile(
    r"\s(?:ngay\s+)?(?P<prep>vào trong|vào|trong|dưới|sau|ở|tại|trước)\s+"
    r"(?P<kind>phần|mục|heading|tiêu đề|dòng|to-do|todo|đoạn văn|đoạn|block)\s+(?P<name>.+?)\s*$",
    re.IGNORECASE,
)
PLACE_EN = re.compile(
    r"\s(?P<prep>under|after|before|in|into|to|below|above)\s+the\s+(?P<name>.+?)\s+(?P<kind>section|heading)\s*$",
    re.IGNORECASE,
)
PLACE_EN_AFTER = re.compile(r"\s(?P<prep>after|below)\s+(?!the\s)(?P<name>.+?)\s*$", re.IGNORECASE)
BEFORE = {"trước", "before", "above"}
SECTION_KINDS = {"phần", "mục", "heading", "tiêu đề", "section"}
HEADER_LEVEL = 2  # DF3


def _block(kind: str, text: str) -> dict[str, Any]:
    if kind == "TODO":
        return {"type": "TODO", "content": {"text": strip_list_marker(text), "checked": False}}
    if kind == "HEADER":
        return {"type": "HEADER", "content": {"text": text}, "styleConfig": {"level": HEADER_LEVEL}}
    return {"type": kind, "content": {"text": text}}


# S1 (kế hoạch sửa lỗi người dùng giả lập): "vào Môn Toán", "vô môn toán",
# "to Packing" name a section without "phần": only when the words are exactly
# one root heading / toggle of the Page. Otherwise they stay content.
BARE_PLACE = re.compile(r"\s(?:vào|vô|trong|to|in|into|under)\s+(?:the\s+)?(?P<name>[^,.;:!?\"“”]+?)\s*[.!]*$",
                        re.IGNORECASE)
PLACE_WORDS = {"vao", "vo", "trong", "to", "in", "into", "under", "cho"}


def _sections(context: AiPageContext) -> list[Any]:
    return [block for block in context.blocks
            if block.parentBlockId is None and block.type in ("HEADER", "TOGGLE") and _text_of(block)]


def _with_bare_place(instruction: str, context: AiPageContext) -> str:
    """ "… vào Môn Toán" as "… vào phần Môn Toán" when Môn Toán is one section."""
    match = BARE_PLACE.search(instruction)
    if match is None:
        return instruction
    name = match.group("name").strip()
    same = [block for block in _sections(context) if text_key(_text_of(block)) == text_key(name)]
    if len(same) != 1:
        return instruction
    return f"{instruction[:match.start()]} vào phần {name}"


PLACE_FIRST_LOOSE = re.compile(r"^(?P<lead>ghi them vao|them vao)\s+(?P<rest>.+)$")


def _place_named_first(instruction: str, context: AiPageContext) -> str:
    """Bước 4 (bỏ dấu hai chấm): "ghi thêm vào Tuần họp dời họp sang thứ Năm" /
    "thêm vào phần Tuần họp chuẩn bị slide, gửi lịch": the section name is where a
    real heading / toggle name ends; it then reads like the ":" form."""
    if ":" in instruction:
        return instruction
    folded = Folded(instruction)
    match = PLACE_FIRST_LOOSE.match(folded.value)
    if match is None:
        return instruction
    rest = match.group("rest")
    word = re.match(r"(?:phan|muc)\s+", rest)
    start = word.end() if word else 0
    names = sorted({fold(strip_list_marker(_text_of(block))) for block in _sections(context)}, key=len, reverse=True)
    for name in names:
        if rest[start:].startswith(name + " ") and len(rest) > start + len(name) + 1:
            cut = match.start("rest") + start + len(name)
            head = folded.original(0, cut).strip()
            text = folded.original(cut, len(folded.value)).strip()
            return normalize_instruction(f"{head}: {text}")
    return instruction


def _ends_with_a_place(blocks: list[tuple[str, str]], context: AiPageContext) -> bool:
    """Safety net: content ending in "vào <a section name>" was not read cleanly."""
    names = {text_key(_text_of(block)) for block in _sections(context)}
    for _, value in blocks:
        words = text_key(value).split()
        for name in names:
            size = len(name.split())
            if size and len(words) > size and " ".join(words[-size:]) == name and words[-size - 1] in PLACE_WORDS:
                return True
    return False


def plan_explicit_content(
    instruction: str, context: AiPageContext, references: Any,
) -> AiModificationPlan | None:
    if references:
        return None
    instruction = _with_bare_place(_place_named_first(instruction, context), context)
    blocks = parse_explicit_blocks(instruction)
    if blocks is None or _ends_with_a_place(blocks, context):
        return None
    text, _, _page_end = _command(instruction, context.page.title)
    place = _named_place(text, context) if POSITION.search(text) else _end_of_page(context)
    if place is None:
        return None
    # "thêm checklist ngày đầu tiên" on a Page with a heading "Ngày đầu tiên" may
    # mean that section: content equal to a block already there is the model's call.
    existing = {
        text_key(block.content["text"]) for block in context.blocks
        if isinstance(block.content, dict) and isinstance(block.content.get("text"), str)
    }
    if any(text_key(value) in existing for _, value in blocks):
        return None
    parent, after = place
    return PLAN_ADAPTER.validate_python({
        "schemaVersion": 1, "type": "AI_MODIFICATION_PLAN", "pageId": context.page.id,
        "status": "PLAN_READY", "summary": instruction.strip(),
        "operations": [{"type": "INSERT_BLOCKS", "parentBlockId": parent, "afterBlockId": after,
                        "blocks": [_block(kind, value) for kind, value in blocks]}],
    })


def _end_of_page(context: AiPageContext) -> tuple[str | None, str | None]:
    roots = [block for block in context.blocks if block.parentBlockId is None]
    return None, (max(roots, key=lambda block: block.orderIndex).id if roots else None)


def _text_of(block: Any) -> str | None:
    text = block.content.get("text") if isinstance(block.content, dict) else None
    return text if isinstance(text, str) else None


def _named_place(text: str, context: AiPageContext) -> tuple[str | None, str | None] | None:
    """(parentBlockId, afterBlockId) for a place the sentence names, or None when unsure."""
    match = PLACE_VI.search(text) or PLACE_EN.search(text) or PLACE_EN_AFTER.search(text)
    if match is None or match.group("prep").casefold() in BEFORE:
        return None
    name = match.group("name").strip(" .,!")
    kind = (match.groupdict().get("kind") or "").casefold()
    if kind in SECTION_KINDS:
        sections = [block for block in context.blocks if block.parentBlockId is None
                    and block.type in ("HEADER", "TOGGLE") and text_key(_text_of(block) or "") == text_key(name)]
        if len(sections) > 1:
            return None
        if sections:
            # "dưới heading X" / "under the X heading": right below that heading;
            # "vào phần X" / "under the X section": at the end of the section.
            prep = match.group("prep").casefold()
            if sections[0].type == "HEADER" and prep in {"dưới", "under", "below"} and kind in {"heading", "tiêu đề"}:
                return None, sections[0].id
            return _inside(sections[0], context)
    # A line ("sau dòng X"), or a section name that is a line of text ("sau phần ghi chú").
    found = match_exact(name, text_blocks(context)) or match_partial(name, text_blocks(context))
    if found is None or len(found.blocks) != 1:
        return None
    block = next(block for block in context.blocks if block.id == found.blocks[0].block_id)
    return block.parentBlockId, block.id


def _inside(section: Any, context: AiPageContext) -> tuple[str | None, str | None]:
    if section.type == "TOGGLE":
        children = sorted((block for block in context.blocks if block.parentBlockId == section.id),
                          key=lambda block: block.orderIndex)
        return section.id, (children[-1].id if children else None)
    roots = sorted((block for block in context.blocks if block.parentBlockId is None),
                   key=lambda block: block.orderIndex)
    start = roots.index(section)
    end = start
    for index in range(start + 1, len(roots)):
        if roots[index].type == "HEADER":
            break
        end = index
    return None, roots[end].id
