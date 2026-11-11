import asyncio
import importlib.util
import re
from types import SimpleNamespace

import pytest

from app.core.exceptions import (
    DraftNotDoneError,
    InvalidLLMResponseError,
    LLMProviderError,
    LLMTimeoutError,
    LLMUnavailableError,
    WritingNotDoneError,
)
from evaluation.natural_vi_generator import DEV_BANK, DEV_SEED, bank_words, command_count, generate
from scripts.evaluate_end_to_end import error_stop, run_cases
from scripts.evaluate_generation import CONTEXTS
from scripts.evaluate_natural_vi import (
    ASK,
    DRAFT,
    OK,
    PAGE,
    SYSTEM,
    final_outcome,
    load_seed,
    measure,
    modify_outcome,
    question_outcome,
    summarize,
    writing_outcome,
)

MARKS = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.IGNORECASE)
AWKWARD = re.compile(r"^(?:bạn|nhờ bạn|cho mình|giúp mình) (?:trang |ở trang|trong trang|mình )", re.IGNORECASE)
HOLDOUT = "evaluation.natural_vi_holdout_forms"


def problems(cases: list[dict]) -> int:
    return sum(
        not MARKS.search(case["instruction"]) or ":" in case["instruction"] or '"' in case["instruction"]
        or bool(AWKWARD.search(case["instruction"])) or case["instruction"].count("giúp mình") > 1
        for cases_of in [cases] for case in cases_of
    )


def holdout_bank() -> dict:
    if importlib.util.find_spec(HOLDOUT) is None:
        pytest.skip("holdout forms not written yet")
    return importlib.import_module(HOLDOUT).BANK


def test_same_seed_gives_same_sentences() -> None:
    assert generate(DEV_BANK, DEV_SEED) == generate(DEV_BANK, DEV_SEED)
    assert generate(DEV_BANK, DEV_SEED)["modify"] != generate(DEV_BANK, 777)["modify"]


def test_each_capability_has_one_hundred_cases_with_group_and_expect() -> None:
    sets = generate(DEV_BANK, DEV_SEED)
    assert sorted(sets) == ["compose", "modify", "question", "writing"]
    for cases in sets.values():
        assert len(cases) == 100
        assert len({case["id"] for case in cases}) == 100
        assert all(case["group"] and "expect" in case for case in cases)


@pytest.mark.parametrize("seed", [DEV_SEED, 777, 12345])
def test_sentences_are_natural(seed: int) -> None:
    sets = generate(DEV_BANK, seed)
    assert sum(problems(cases) for cases in sets.values()) == 0


def test_writing_commands_are_at_least_doubled() -> None:
    assert command_count(DEV_BANK) >= 66


def test_inline_writing_sentence_carries_its_source() -> None:
    inline = [case for case in generate(DEV_BANK, DEV_SEED)["writing"] if case["group"] == "inline"]
    assert len(inline) == 20
    assert all(not case.get("selectedText") and case["expect"]["source"] in case["instruction"] for case in inline)


def test_some_sentences_name_a_page_other_than_the_open_one() -> None:
    group = [case for case in generate(DEV_BANK, DEV_SEED)["modify"] if case["group"] == "other_page_open"]
    assert len(group) == 12
    assert all(case["current"] and DEV_BANK["modify"]["pages"][case["page"]] in case["instruction"] for case in group)


def fixture_mismatches(bank: dict, contexts: dict, question_contexts: dict, seed: int) -> int:
    sets = generate(bank, seed)
    bad = 0
    for case in sets["modify"]:
        context = contexts.get(case["page"])
        if context is None or context["page"]["title"] != bank["modify"]["pages"][case["page"]]:
            bad += 1
            continue
        known = {block["id"] for block in context["blocks"]}
        expect = case["expect"]
        wanted = set(expect.get("blocks", [])) | {expect[key] for key in ("after", "parent") if key in expect}
        bad += not wanted <= known
    for case in sets["question"]:
        name = case["expect"].get("context")
        if name is not None:
            context = question_contexts.get(name)
            bad += context is None or context["page"]["title"] != bank["question"]["pages"].get(name)
    return bad


def test_dev_expectations_point_at_real_blocks() -> None:
    from scripts.evaluate_page_question import CONTEXTS as QUESTION_CONTEXTS

    assert fixture_mismatches(DEV_BANK, CONTEXTS, QUESTION_CONTEXTS, DEV_SEED) == 0


def test_holdout_expectations_point_at_real_blocks() -> None:
    bank = holdout_bank()
    bad = fixture_mismatches(bank, bank["contexts"], bank["question_contexts"], 4242)
    assert bad == 0


def test_holdout_is_separate_from_dev() -> None:
    bank = holdout_bank()
    shared_words = len(bank_words(bank) & bank_words(DEV_BANK))
    dev = {case["instruction"] for cases in generate(DEV_BANK, DEV_SEED).values() for case in cases}
    held = {case["instruction"] for cases in generate(bank, 4242).values() for case in cases}
    shared_sentences = len(dev & held)
    assert shared_words == 0
    assert shared_sentences == 0


def test_holdout_sentences_are_natural_and_complete() -> None:
    sets = generate(holdout_bank(), 4242)
    sizes = sorted(len(cases) for cases in sets.values())
    bad = sum(problems(cases) for cases in sets.values())
    assert sizes == [100, 100, 100, 100]
    assert bad == 0


def test_final_outcome_takes_the_majority_of_an_ordinary_case() -> None:
    assert final_outcome([OK, DRAFT, OK], must_stop=False) == OK
    assert final_outcome([DRAFT, OK, DRAFT], must_stop=False) == DRAFT


def test_final_outcome_takes_the_worst_of_three_different() -> None:
    assert final_outcome([OK, ASK, DRAFT], must_stop=False) == DRAFT
    assert final_outcome([OK, ASK, SYSTEM], must_stop=False) == SYSTEM


def test_one_wrong_page_is_a_wrong_page() -> None:
    assert final_outcome([OK, OK, PAGE], must_stop=False) == PAGE


def test_a_case_that_must_stop_needs_three_of_three() -> None:
    assert final_outcome([OK, OK, DRAFT], must_stop=True) == DRAFT
    assert final_outcome([OK, OK, OK], must_stop=True) == OK
    assert final_outcome([OK, SYSTEM, OK], must_stop=True) == SYSTEM
    assert final_outcome([OK, ASK, OK], must_stop=True) == ASK


def test_a_rules_only_case_is_its_one_result() -> None:
    assert final_outcome([DRAFT], must_stop=False) == DRAFT


def outcome_of(stop: str, expect: dict, failed: list | None = None, page: str | None = "A") -> str:
    return modify_outcome({"stop": stop, "failed": failed or [], "pageTitle": page}, expect, "A")


def test_modify_outcomes() -> None:
    wanted = {"op": "INSERT_BLOCKS"}
    assert outcome_of("draft", wanted) == OK
    assert outcome_of("draft", wanted, ["texts"]) == DRAFT
    assert outcome_of("draft", wanted, page="B") == PAGE
    assert outcome_of("wrong-page", wanted, page="B") == PAGE
    assert outcome_of("intent:UNCLEAR", wanted) == ASK
    assert outcome_of("intent:OTHER", wanted) == ASK
    assert outcome_of("intent:CREATE_PAGE", wanted) == DRAFT
    assert outcome_of("nestjs:UNSUPPORTED_OPERATION", wanted) == ASK
    assert outcome_of("nestjs-ask:AMBIGUOUS", wanted) == ASK
    assert outcome_of("planner-ask", wanted) == ASK
    assert outcome_of("not-done:DraftNotDoneError", wanted) == ASK
    assert outcome_of("system:LLMTimeoutError", wanted) == SYSTEM


def test_modify_outcomes_of_cases_that_must_stop() -> None:
    assert outcome_of("nestjs:UNSUPPORTED_OPERATION", {"refuse": True}) == OK
    assert outcome_of("intent:OTHER", {"refuse": True}) == OK
    assert outcome_of("draft", {"refuse": True}) == DRAFT
    assert outcome_of("nestjs-ask:AMBIGUOUS", {"refuse": True}) == ASK
    assert outcome_of("planner-ask", {"ask": True}) == OK
    assert outcome_of("draft", {"ask": True}) == DRAFT


def test_writing_outcomes() -> None:
    wanted = {"action": "TRANSLATE", "language": "English", "source": "Xin chào cả nhà"}
    good = {"intent": "WRITING", "action": "TRANSLATE", "language": "English", "source": "Xin chào cả nhà", "failed": []}
    assert writing_outcome(good, wanted) == OK
    assert writing_outcome({**good, "source": "cả nhà"}, wanted) == DRAFT
    assert writing_outcome({**good, "source": None}, wanted) == ASK
    assert writing_outcome({**good, "action": "SHORTEN"}, wanted) == DRAFT
    assert writing_outcome({**good, "failed": ["copied"]}, wanted) == DRAFT
    assert writing_outcome({**good, "intent": "UNCLEAR"}, wanted) == ASK
    assert writing_outcome({**good, "error": "not-done:WritingNotDoneError"}, wanted) == ASK
    assert writing_outcome({**good, "error": "system:LLMTimeoutError"}, wanted) == SYSTEM
    assert writing_outcome({**good, "source": None}, {"ask": True}) == OK
    assert writing_outcome(good, {"ask": True}) == DRAFT


def test_question_outcomes() -> None:
    known = {"hội họp tuần", "hội họp"}
    assert question_outcome({"intent": "PAGE_QUESTION", "failed": []}, known) == OK
    assert question_outcome({"intent": "UNCLEAR", "failed": ["intent=UNCLEAR/None"]}, known) == ASK
    assert question_outcome({"intent": "MODIFY_PAGE", "failed": ["intent=MODIFY_PAGE/None"]}, known) == DRAFT
    assert question_outcome({"intent": "PAGE_QUESTION", "failed": ["missing:7"]}, known) == DRAFT
    assert question_outcome({"intent": "PAGE_QUESTION", "failed": ["page=Hội họp"], "reference": "Hội họp"}, known) == PAGE
    assert question_outcome({"intent": "PAGE_QUESTION", "failed": ["page=None"], "reference": None}, known) == PAGE
    assert question_outcome({"intent": "PAGE_QUESTION", "failed": ["page=Lạ"], "reference": "Lạ"}, known) == ASK
    assert question_outcome({"intent": "PAGE_QUESTION", "failed": ["error=WRITING_NOT_DONE:x"]}, known) == ASK
    assert question_outcome({"intent": "PAGE_QUESTION", "failed": [], "error": "system:LLMTimeoutError"}, known) == SYSTEM


@pytest.mark.parametrize("error, stop", [
    (WritingNotDoneError("copied"), "not-done:WritingNotDoneError"),
    (DraftNotDoneError(), "not-done:DraftNotDoneError"),
    (LLMTimeoutError("x"), "system:LLMTimeoutError"),
    (InvalidLLMResponseError("x"), "system:InvalidLLMResponseError"),
    (LLMProviderError("x"), "system:LLMProviderError"),
])
def test_known_errors_are_named(error: Exception, stop: str) -> None:
    assert error_stop(error) == stop


@pytest.mark.parametrize("error", [LLMUnavailableError("x"), KeyError("x")])
def test_unavailable_model_and_unknown_errors_end_the_run(error: Exception) -> None:
    with pytest.raises(type(error)):
        error_stop(error)


def response(result: dict, provider: str = "deterministic") -> SimpleNamespace:
    return SimpleNamespace(result=SimpleNamespace(**result, model_dump=lambda mode: result), provider=provider, model="m")


class Fake:
    def __init__(self, result: dict | Exception, provider: str = "deterministic") -> None:
        self.result, self.provider, self.calls = result, provider, 0

    async def process(self, request: object) -> SimpleNamespace:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return response(self.result, self.provider)


CASE = {"id": "c1", "instruction": "thêm việc gọi khách vào trang sub man", "page": "sub_man",
        "expect": {"op": "INSERT_BLOCKS"}}
PAGE_INTENT = {"intent": "MODIFY_PAGE", "referenceType": "TITLE", "pageReference": "sub man", "instruction": "thêm việc gọi khách"}
PLAN = {"status": "PLAN_READY", "operations": [{"type": "INSERT_BLOCKS"}]}


def services(planner: Fake) -> SimpleNamespace:
    return SimpleNamespace(intents=Fake({"intent": "MODIFY_PAGE"}), pages=Fake(PAGE_INTENT), planner=planner)


def probe_saying(answers: list[dict]) -> tuple:
    seen: list[list[dict]] = []

    def probe(items: list[dict]) -> dict:
        seen.append(items)
        return {item["id"]: answers[len(seen) - 1] for item in items}

    return probe, seen


ADMITTED = {"stage": "admitted", "status": "PLAN_GENERATED", "pageTitle": "sub man"}


def run(planner: Fake, answers: list[dict], **extra: object) -> tuple:
    probe, seen = probe_saying(answers)
    rows = asyncio.run(run_cases([CASE], services(planner), probe, CONTEXTS, **extra))
    return rows, seen


def test_planner_is_not_called_for_a_sentence_nestjs_refuses() -> None:
    planner = Fake(RuntimeError("the planner must not run"))
    rows, seen = run(planner, [{"stage": "refused", "status": "UNSUPPORTED_OPERATION"}])
    assert planner.calls == 0
    assert rows[0]["stop"] == "nestjs:UNSUPPORTED_OPERATION"
    assert len(seen) == 1 and "plan" not in seen[0][0]


def test_nestjs_checks_the_draft_after_the_planner() -> None:
    planner = Fake(PLAN, "ollama")
    rows, seen = run(planner, [ADMITTED, {"stage": "refused", "status": "OPERATION_KIND"}])
    assert planner.calls == 1
    assert seen[1][0]["plan"] == PLAN
    assert rows[0]["stop"] == "nestjs:OPERATION_KIND"
    assert rows[0]["usedModel"] is True


def test_planner_is_not_called_on_the_wrong_page() -> None:
    planner = Fake(PLAN)
    rows, _ = run(planner, [{**ADMITTED, "pageTitle": "Nhật ký"}],
                  pages=[{"id": "1", "title": "sub man"}, {"id": "2", "title": "Nhật ký"}])
    assert planner.calls == 0
    assert rows[0]["stop"] == "wrong-page"
    assert rows[0]["pageTitle"] == "Nhật ký"


def test_rules_only_sentence_is_not_marked_as_model() -> None:
    rows, _ = run(Fake(PLAN), [ADMITTED, ADMITTED])
    assert rows[0]["stop"] == "draft" and rows[0]["usedModel"] is False


def test_model_timeout_is_a_system_stop_and_outage_ends_the_run() -> None:
    rows, _ = run(Fake(LLMTimeoutError("x")), [ADMITTED])
    assert rows[0]["stop"] == "system:LLMTimeoutError"
    with pytest.raises(LLMUnavailableError):
        run(Fake(LLMUnavailableError("x")), [ADMITTED])


def attempts_of(outcomes: dict[str, list[str]], models: dict[str, bool]) -> tuple:
    calls: list[list[str]] = []

    async def once(cases: list[dict]) -> list[dict]:
        calls.append([case["id"] for case in cases])
        turn = len(calls) - 1
        return [{"id": case["id"], "outcome": outcomes[case["id"]][turn], "usedModel": models[case["id"]]} for case in cases]

    return once, calls


def test_only_sentences_that_used_the_model_run_three_times() -> None:
    cases = [{"id": "a", "group": "g", "instruction": "x", "expect": {}}, {"id": "b", "group": "g", "instruction": "y", "expect": {}}]
    once, calls = attempts_of({"a": [OK], "b": [OK, DRAFT, OK]}, {"a": False, "b": True})
    results = asyncio.run(measure(cases, once))
    assert calls == [["a", "b"], ["b"], ["b"]]
    by_id = {result["id"]: result for result in results}
    assert by_id["a"]["runs"] == 1 and by_id["a"]["stable"] is True
    assert by_id["b"]["outcome"] == OK and by_id["b"]["stable"] is False and by_id["b"]["allOk"] is False


def test_cases_that_must_stop_are_scored_strictly_when_measured() -> None:
    cases = [{"id": "a", "group": "g", "instruction": "x", "expect": {"refuse": True}}]
    once, _ = attempts_of({"a": [OK, DRAFT, OK]}, {"a": True})
    assert asyncio.run(measure(cases, once))[0]["outcome"] == DRAFT


SECRET_SENTENCE = "câu bí mật của holdout"
RESULTS = {"modify": [{"id": "h1", "group": "tick", "instruction": SECRET_SENTENCE, "outcome": OK, "stable": False,
                       "allOk": False, "runs": 3, "attempts": [{"instruction": SECRET_SENTENCE}]}]}


def test_summary_counts_every_outcome_by_group() -> None:
    summary = summarize(RESULTS, hide_sentences=False)
    assert summary["modify"]["total"] == {"cases": 1, OK: 1, ASK: 0, SYSTEM: 0, DRAFT: 0, PAGE: 0, "allOk": 0, "unstable": 1}
    assert summary["modify"]["groups"]["tick"][OK] == 1
    assert summary["modify"]["unstable"] == ["h1"]


def test_holdout_summary_holds_no_sentence() -> None:
    summary = summarize(RESULTS, hide_sentences=True)
    assert SECRET_SENTENCE not in str(summary)
    assert "h1" not in str(summary)


def test_seed_is_made_once_and_never_printed(tmp_path, capsys) -> None:
    path = tmp_path / "results" / "holdout_seed.txt"
    first = load_seed(path)
    assert load_seed(path) == first
    assert path.read_text(encoding="utf-8").strip() == str(first)
    assert str(first) not in capsys.readouterr().out
