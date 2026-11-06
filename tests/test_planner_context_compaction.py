import json

from app.modules.modification_planner.schemas.modification_planner_schema import AiPageContext
from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService
from scripts.evaluate_generation import CONTEXTS


def compact(name: str) -> dict:
    return ModificationPlannerService(None)._serialize_context(AiPageContext.model_validate(CONTEXTS[name]))


def test_prompt_context_drops_metadata_but_keeps_what_the_planner_reads() -> None:
    # Kế hoạch tạo trang + rút gọn ngữ cảnh (D.2): reading the prompt was 31–42%
    # of the planner on 20–30 block pages; validators still see the full context.
    data = compact("study")
    assert "schemaVersion" not in data and "builtAt" not in data
    assert data["page"] == {"id": "page-1", "title": "Ôn thi cuối kỳ"}
    assert "completeness" not in data  # nothing was cut
    header = data["blocks"][0]
    assert header == {"id": "s0", "parentBlockId": None, "type": "HEADER", "orderIndex": 0,
                      "content": {"text": "Môn Toán"}, "styleConfig": {"level": 1}}
    child = next(block for block in data["blocks"] if block["id"] == "s6")
    assert child["parentBlockId"] == "s5" and "title" not in child and "dataConfig" not in child


def test_prompt_context_keeps_databases_whole() -> None:
    # Dropping "views" lost the TITLE column in live runs (gp28, gp30 0/3): kept.
    database = compact("reading")["databases"][0]
    assert database["views"][0]["properties"][0]["propertyId"] == "q-name"
    assert [p["id"] for p in database["properties"]] == ["q-name", "q-state"]
    assert {o["id"] for o in database["properties"][1]["options"]} == {"o-reading", "o-read"}
    assert database["rows"][0]["values"] == {"q-name": "Nhà giả kim", "q-state": "o-read"}


def test_truncation_is_still_reported() -> None:
    raw = json.loads(json.dumps(CONTEXTS["study"]))
    raw["completeness"]["textTruncated"] = True
    data = ModificationPlannerService(None)._serialize_context(AiPageContext.model_validate(raw))
    assert data["completeness"]["textTruncated"] is True


def test_compact_context_is_smaller() -> None:
    for name in ("meeting", "study", "reading"):
        full = AiPageContext.model_validate(CONTEXTS[name]).model_dump(mode="json", exclude_unset=True)
        assert len(json.dumps(compact(name))) < 0.75 * len(json.dumps(full))
