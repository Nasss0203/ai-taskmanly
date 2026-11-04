"""Regression cases: raw teacher labels must pass before app repair."""
import asyncio
import json
from pathlib import Path

import pytest

from tests.fakes.fake_async_llm_provider import FakeLLMProvider
from training.teacher import answer, run

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "training_raw_labels.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case["example"]["id"])
def test_rejects_stored_labels_that_only_pass_after_repair(case):
    provider = FakeLLMProvider(case["responses"])
    result = asyncio.run(answer(case["example"], provider))
    assert not result["kept"], result
    assert "chats" not in result
    assert result["reason"].startswith("raw_"), result


def test_clean_sourced_label_is_kept_without_rewriting():
    case = next(c for c in FIXTURES if c["example"]["id"] == "t0014")
    generation = json.dumps({"operations": case["clean_plan"]["operations"]}, ensure_ascii=False)
    result = asyncio.run(answer(case["example"], FakeLLMProvider([case["responses"][0], generation])))
    assert result["kept"], result
    assert len(result["chats"]) == 2
    assert result["chats"][1]["messages"][-1]["content"] == generation


def test_resume_refuses_legacy_log_without_modifying_existing_files(tmp_path):
    case = FIXTURES[0]
    requests = tmp_path / "requests.jsonl"
    requests.write_text(json.dumps(case["example"]), encoding="utf-8")
    output = tmp_path / "sft.jsonl"
    log = tmp_path / "sft.log.jsonl"
    output.write_text("old dataset\n", encoding="utf-8")
    log.write_text(json.dumps({"id": case["example"]["id"], "kept": True}) + "\n", encoding="utf-8")
    provider = FakeLLMProvider([])
    with pytest.raises(ValueError, match="filter version"):
        asyncio.run(run(requests, output, provider, None))
    assert output.read_text(encoding="utf-8") == "old dataset\n"
    assert json.loads(log.read_text(encoding="utf-8"))["kept"] is True
    assert provider.calls == []


def test_resume_refuses_unlogged_dataset(tmp_path):
    requests = tmp_path / "requests.jsonl"
    requests.write_text("", encoding="utf-8")
    output = tmp_path / "sft.jsonl"
    output.write_text("old dataset\n", encoding="utf-8")
    with pytest.raises(ValueError, match="without a matching log"):
        asyncio.run(run(requests, output, FakeLLMProvider([]), None))
    assert output.read_text(encoding="utf-8") == "old dataset\n"
