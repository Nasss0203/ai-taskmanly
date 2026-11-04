"""Kế hoạch train Colab (T2, T3, T7): synthetic requests and teacher filtering."""

import asyncio
import json

import pytest

from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
from tests.fakes.fake_async_llm_provider import FakeLLMProvider
from training.prepare_dataset import (
    RESERVED_TITLES,
    RESERVED_WORDS,
    answered_by_rules,
    fold,
    generate,
    reserved_sentences,
)
from training.teacher import answer, extra_failures, run


@pytest.fixture(scope="module")
def examples():
    return generate(150, seed=3)


def test_generation_is_repeatable():
    assert generate(20, seed=3) == generate(20, seed=3)
    assert generate(20, seed=3) != generate(20, seed=4)


def test_every_request_is_valid_and_needs_the_model(examples):
    assert len(examples) == 150
    for example in examples:
        request = ModificationPlannerRequest.model_validate(example["request"])
        assert not answered_by_rules(request), example["request"]["instruction"]


def test_evaluation_pages_and_sentences_stay_out(examples):
    reserved = reserved_sentences()
    assert "them checklist chuan bi release" in reserved  # gp02
    for example in examples:
        instruction = fold(example["request"]["instruction"])
        title = example["request"]["context"]["page"]["title"]
        assert title.casefold() not in RESERVED_TITLES
        assert not RESERVED_WORDS.search(instruction) and not RESERVED_WORDS.search(fold(title))
        assert instruction not in reserved


def test_items_are_new_and_sources_have_no_heading(examples):
    for example in examples:
        context = example["request"]["context"]
        existing = {fold(b["content"]["text"]) for b in context["blocks"] if isinstance(b.get("content"), dict)}
        for item in example["expect"].get("todo_texts", []):
            assert fold(item) not in existing
        for reference in example["request"].get("references", []):
            assert "section" not in reference and "isHeading" not in reference


def test_only_free_wording_is_typed_without_accents(examples):
    for example in examples:
        instruction = example["request"]["instruction"]
        if instruction == fold(instruction) and example["lang"] == "vi":
            assert example["kind"] in {"references", "topic_checklist", "missing_section"}


def _route(operation="INSERT_BLOCKS"):
    return json.dumps({"status": "PLAN_READY", "operationTypes": [operation]})


def _checklist_example():
    for example in generate(80, seed=11):
        if example["kind"] == "checklist" and "after_block" not in example["expect"]:
            return example
    raise AssertionError("no plain checklist example")


def _insert(items, after=None):
    """The operations step's answer: operations only, the service adds the rest."""
    return json.dumps({
        "operations": [{"type": "INSERT_BLOCKS", "parentBlockId": None, "afterBlockId": after,
                        "blocks": [{"type": "TODO", "content": {"text": item, "checked": False}} for item in items]}],
    })


def test_teacher_keeps_a_right_plan_as_two_chats():
    example = _checklist_example()
    provider = FakeLLMProvider([_route(), _insert(example["expect"]["todo_texts"])])
    result = asyncio.run(answer(example, provider))
    assert result["kept"], result
    assert [len(chat["messages"]) for chat in result["chats"]] == [3, 3]
    first, second = result["chats"]
    # The exact prompts the planner sent, and the teacher's raw answers.
    assert first["messages"][0]["content"] == provider.calls[0]["system_prompt"]
    assert second["messages"][1]["content"] == provider.calls[1]["user_prompt"]
    assert json.loads(second["messages"][2]["content"])["operations"][0]["type"] == "INSERT_BLOCKS"


def test_teacher_drops_a_valid_but_wrong_plan():
    example = _checklist_example()
    wrong = example["expect"]["todo_texts"][:-1] + ["Một việc tự nghĩ ra"]
    result = asyncio.run(answer(example, FakeLLMProvider([_route(), _insert(wrong)])))
    assert not result["kept"] and "todo_texts" in result["reason"]


def test_teacher_drops_invalid_json():
    result = asyncio.run(answer(_checklist_example(), FakeLLMProvider([_route(), "{not json"])))
    assert not result["kept"]


def test_sourced_to_dos_must_come_from_the_passages():
    expect = {"todos_from": ["Học từ vựng theo chủ đề", "Nghe podcast khi đi đường"], "min_todos": 1}
    plan = json.loads(_insert(["Học từ vựng theo chủ đề"]))
    assert extra_failures(plan, expect) == []
    plan = json.loads(_insert(["Học từ vựng theo chủ đề", "Đi du học"]))
    assert extra_failures(plan, expect) == ["todos_from"]
    assert extra_failures(json.loads(_insert([])), expect) == ["min_todos"]


def test_run_carries_on_after_an_interruption(tmp_path):
    example = _checklist_example()
    requests = tmp_path / "requests.jsonl"
    requests.write_text("\n".join(json.dumps({**example, "id": f"t{i}"}, ensure_ascii=False) for i in (1, 2)),
                        encoding="utf-8")
    output = tmp_path / "sft.jsonl"
    items = example["expect"]["todo_texts"]
    first = asyncio.run(run(requests, output, FakeLLMProvider([_route(), _insert(items)]), limit=1))
    second = asyncio.run(run(requests, output, FakeLLMProvider([_route(), _insert(items)]), limit=None))
    assert (first["kept"], second["kept"], second["alreadyDone"]) == (1, 1, 1)
    assert len(output.read_text(encoding="utf-8").splitlines()) == 4


# Decoded from the context tokens Ollama 0.40.13 renders for qwen3:1.7b with
# think=false (2026-11-01): training text must match it character for character.
OLLAMA_RENDERED = (
    "<|im_start|>system\n\nSYS LINE<|im_end|>\n<|im_start|>user\nUSER LINE /no_think<|im_end|>\n"
    "<|im_start|>assistant\n<think>\n\n</think>\n\n"
)


def test_training_text_is_what_ollama_feeds_the_model():
    from training.chat_format import END, render_example, render_prompt

    assert render_prompt("SYS LINE", "USER LINE") == OLLAMA_RENDERED
    example = render_example({"messages": [
        {"role": "system", "content": "SYS LINE"}, {"role": "user", "content": "USER LINE"},
        {"role": "assistant", "content": '{"status": "PLAN_READY"}'},
    ]})
    assert example == {"prompt": OLLAMA_RENDERED, "completion": '{"status": "PLAN_READY"}' + END}


def test_modelfile_keeps_the_base_template_and_points_at_the_gguf(tmp_path):
    from training.make_modelfile import modelfile

    base = (
        "# Modelfile generated by \"ollama show\"\n# To build a new Modelfile...\n\n"
        "FROM C:\models\blobs\sha256-abc\n"
        'TEMPLATE """{{ if .Tools }}\n# Tools\n{{ end }}<|im_start|>assistant"""\n'
        "PARAMETER stop <|im_start|>\nPARAMETER stop <|im_end|>\n"
    )
    out = modelfile(base, tmp_path / "planner.gguf").splitlines()
    assert out[0] == "FROM ./planner.gguf"
    assert sum(line.startswith("FROM ") for line in out) == 1
    assert "# Tools" in out and out.count("PARAMETER stop <|im_end|>") == 1


def test_colab_bundle_has_the_planner_and_no_secrets(tmp_path):
    import zipfile

    from training.make_colab_bundle import bundle

    output = tmp_path / "bundle.zip"
    bundle(output)
    names = set(zipfile.ZipFile(output).namelist())
    for required in ("app/modules/modification_planner/services/modification_planner_service.py",
                     "scripts/evaluate_generation.py", "training/teacher.py", "training/chat_format.py",
                     "training/__init__.py", "training/data/requests.jsonl"):
        assert required in names
    assert not any(name.endswith(".env") or "__pycache__" in name for name in names)


def test_notebook_is_valid_and_its_code_parses():
    import ast

    from training.build_notebook import build

    notebook = json.loads(json.dumps(build()))
    assert notebook["nbformat"] == 4 and notebook["metadata"]["colab"]["gpuType"] == "T4"
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            ast.parse("\n".join("pass" if line.lstrip().startswith("!") else line for line in source.splitlines()))
