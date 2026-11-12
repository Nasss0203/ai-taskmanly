"""M8 (kế hoạch ngữ cảnh RAG): "thêm checklist các bug blocker … dựa trên trang
Bug tracker" takes the items under the source Page's "Bug blocker" heading,
without the model.

Measured on ten sentences, the 4B planner returned only the heading, or no
item at all, for exactly these requests. A named source Page read whole comes
with each passage's heading, so the items can be picked by rule.
"""

import re
import unicodedata

from pydantic import TypeAdapter

from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    ModificationPlannerReference,
)
from app.shared.list_markers import strip_list_marker
from app.shared.vi_vocabulary import pattern


REFERENCE_CHECKLIST_PROVIDER = "rules"
REFERENCE_CHECKLIST_MODEL = "reference-checklist-v1"

PLAN_ADAPTER = TypeAdapter(AiModificationPlan)

# "thêm checklist", "thêm checklist các bug blocker", "add a checklist of blocker bugs"
CHECKLIST = re.compile(
    rf"^(?:{pattern('lead')}\s+)?(?:them|tao|add|create)\s+(?:(?:mot|1|a|an)\s+)?"
    r"(?:checklist|danh sach viec|to-?do list)(?:\s+(?P<topic>.+))?$"
)
# Words that say nothing about which heading is meant.
FILLER = frozenset(
    "cac nhung ve gom tat ca moi of the all for about with".split()
)


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFD", text)
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", folded.replace("đ", "d").replace("Đ", "D").casefold()).strip(" .!?")


def _topic_words(text: str) -> frozenset[str]:
    return frozenset(
        word for word in re.split(r"[^\w]+", _fold(text)) if word and word not in FILLER
    )


def _matches(topic: frozenset[str], heading: str) -> bool:
    """"bug blocker" is "Bug blocker"; "bug blocker can sua" also names it."""
    words = _topic_words(heading)
    return bool(words) and (topic <= words or words <= topic)


def plan_reference_checklist(
    instruction: str,
    page_id: str,
    references: list[ModificationPlannerReference] | None,
) -> AiModificationPlan | None:
    """A checklist of the source items, or None to use the normal planner."""
    if not references or not any(reference.isHeading or reference.section for reference in references):
        return None
    match = CHECKLIST.match(_fold(instruction))
    if not match:
        return None
    items = [reference for reference in references if not reference.isHeading]
    if match.group("topic"):
        topic = _topic_words(match.group("topic"))
        headings = {
            reference.text for reference in references
            if reference.isHeading and _matches(topic, reference.text)
        }
        # No heading names it ("các lỗi cần sửa"): the model reads the passages.
        if not headings:
            return None
        items = [reference for reference in items if reference.section in headings]
    texts = [strip_list_marker(reference.text).strip() for reference in items]
    texts = [text for text in dict.fromkeys(texts) if text]
    if not texts:
        return None
    return PLAN_ADAPTER.validate_python({
        "schemaVersion": 1,
        "type": "AI_MODIFICATION_PLAN",
        "pageId": page_id,
        "status": "PLAN_READY",
        "summary": instruction.strip(),
        "operations": [{
            "type": "INSERT_BLOCKS",
            "parentBlockId": None,
            "afterBlockId": None,
            "blocks": [
                {"type": "TODO", "content": {"text": text, "checked": False}}
                for text in texts
            ],
        }],
    })
