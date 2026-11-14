import asyncio
import json

import pytest

from scripts.probe_intent_gate import check_split, expected, matches, probe_case, summarize
from tests.fakes.fake_async_llm_provider import FakeLLMProvider


def answer(intent, action=None, language=None) -> str:
    return json.dumps({"intent": intent, "writingAction": action, "language": language})


SECTIONS = "mình cần trang Nhật ký đọc sách có ba phần Rủi ro, Mục tiêu và Ghi chú"
COMPOSE = {"id": "c1", "group": "sections", "instruction": SECTIONS, "expect": {"title": "Nhật ký đọc sách"}}


def run(capability, case, local, others=None):
    return asyncio.run(probe_case(capability, case, local, others or {}))


def test_expected_intent_for_each_kind_of_case() -> None:
    assert expected("compose", {"expect": {}})["intents"] == {"CREATE_PAGE"}
    assert expected("compose", {"expect": {"refuse": True}})["intents"] == {"OTHER", "UNCLEAR", "MODIFY_PAGE", "WRITING"}
    assert expected("modify", {"expect": {}})["intents"] == {"MODIFY_PAGE"}
    assert expected("modify", {"expect": {"ask": True}})["intents"] == {"MODIFY_PAGE", "UNCLEAR"}
    assert expected("modify", {"expect": {"refuse": True}})["intents"] == {"OTHER", "UNCLEAR", "MODIFY_PAGE"}
    assert expected("writing", {"expect": {"ask": True}})["intents"] == {"OTHER", "UNCLEAR"}
    want = expected("writing", {"expect": {"action": "TRANSLATE", "language": "English"}})
    assert (want["intents"], want["action"], want["language"]) == ({"WRITING"}, "TRANSLATE", "English")


def test_a_model_answer_must_match_action_and_language() -> None:
    want = expected("writing", {"expect": {"action": "TRANSLATE", "language": "English"}})
    assert matches({"intent": "WRITING", "writingAction": "TRANSLATE", "language": "English"}, want)
    assert not matches({"intent": "WRITING", "writingAction": "SUMMARIZE", "language": None}, want)
    assert not matches({"intent": "WRITING", "writingAction": "TRANSLATE", "language": "French"}, want)
    assert not matches(None, want)


def test_a_case_that_must_stop_is_not_right_when_the_model_creates() -> None:
    want = expected("compose", {"expect": {"refuse": True}})
    assert not matches({"intent": "CREATE_PAGE", "writingAction": None, "language": None}, want)
    assert matches({"intent": "UNCLEAR", "writingAction": None, "language": None}, want)


def test_a_refused_edit_may_reach_nestjs_which_refuses_it() -> None:
    want = expected("modify", {"expect": {"refuse": True}})
    assert matches({"intent": "MODIFY_PAGE", "writingAction": None, "language": None}, want)
    assert not matches({"intent": "CREATE_PAGE", "writingAction": None, "language": None}, want)


def test_rules_deciding_right_need_no_model() -> None:
    local = FakeLLMProvider([])
    row = run("compose", {"id": "c0", "group": "bare", "instruction": "tạo trang Họp tuần", "expect": {}}, local)
    assert (row["final"], row["who"]) == ("CREATE_PAGE", "dung")
    assert local.calls == []


def test_rules_deciding_wrong_still_ask_every_model() -> None:
    case = {"id": "w1", "group": "TRANSLATE", "instruction": "dịch đoạn này sang tiếng Anh",
            "expect": {"action": "TRANSLATE", "language": "English"}}
    local = FakeLLMProvider([answer("WRITING", "TRANSLATE", "English")])
    other = FakeLLMProvider([answer("UNCLEAR")])
    row = run("writing", case, local, {"gemini": other})
    assert (row["final"], row["who"]) == ("UNCLEAR", "luat_quyet")
    assert row["rawRight"] == {"local": True, "gemini": False}
    assert len(local.calls) == 1 and len(other.calls) == 1


def test_a_right_model_answer_lowered_by_the_gate() -> None:
    local = FakeLLMProvider([answer("CREATE_PAGE")])
    row = asyncio.run(probe_case("compose", COMPOSE, local, {}, ["Nhật ký đọc sách"]))
    assert (row["final"], row["who"]) == ("UNCLEAR", "cong_ha")
    assert row["raw"]["local"]["intent"] == "CREATE_PAGE"
    assert row["rawRight"] == {"local": True}
    assert len(local.calls) == 1


def test_a_wrong_model_answer() -> None:
    row = run("compose", COMPOSE, FakeLLMProvider([answer("OTHER")]))
    assert (row["final"], row["who"]) == ("OTHER", "model_sai")
    assert row["rawRight"] == {"local": False}


def test_broken_model_json_is_recorded_and_does_not_stop_the_probe() -> None:
    other = FakeLLMProvider(["not json"])
    row = run("compose", COMPOSE, FakeLLMProvider(["not json", "still not json"]), {"gemini": other})
    assert row["who"] == "loi"
    assert row["raw"] == {"local": "model_loi", "gemini": "model_loi"}
    assert row["rawRight"] == {"local": False, "gemini": False}


def test_summary_counts_stuck_cases_and_the_share_a_model_gets_right() -> None:
    rows = [
        {"capability": "compose", "who": "dung", "rawRight": {}},
        {"capability": "compose", "who": "luat_quyet", "rawRight": {"local": True, "gemini": False}},
        {"capability": "compose", "who": "cong_ha", "rawRight": {"local": True, "gemini": True}},
        {"capability": "compose", "who": "model_sai", "rawRight": {"local": False, "gemini": True}},
        {"capability": "compose", "who": "model_sai", "rawRight": {"local": False, "gemini": False}},
    ]
    entry = summarize(rows)["compose"]
    assert entry == {"cases": 5, "stuck": 4, "luat_quyet": 1, "cong_ha": 1, "model_sai": 2, "loi": 0,
                     "right": {"local": 2, "gemini": 2}, "rightAny": 3, "share": 0.75}


def test_holdout_is_refused() -> None:
    with pytest.raises(ValueError):
        check_split("holdout")
    check_split("dev")
    check_split("dev2")
