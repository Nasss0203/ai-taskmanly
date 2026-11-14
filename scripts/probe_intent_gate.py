import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.exceptions import InvalidLLMResponseError
from app.modules.intent.prompts.intent_prompt import build_intent_prompt
from app.modules.intent.schemas.intent_schema import IntentExtraction, IntentRequest
from app.modules.intent.services.intent_service import IntentService
from app.modules.modification_planner.services.sentence_normalize import normalize_edit_instruction
from app.shared.json_parser import parse_json_object

CAPABILITIES = ("writing", "compose", "modify")
STOP = frozenset({"OTHER", "UNCLEAR"})
LOCAL = "local"
WHO = ("luat_quyet", "cong_ha", "model_sai", "loi")


def check_split(split: str) -> None:
    if split not in ("dev", "dev2"):
        raise ValueError("Probe chỉ chạy trên dev / dev2.")


def expected(capability: str, case: dict[str, Any]) -> dict[str, Any]:
    expect = case["expect"]
    want: dict[str, Any] = {"intents": {"CREATE_PAGE"}, "action": None, "language": None}
    if capability == "compose":
        want["intents"] = set(STOP) if expect.get("refuse") else {"CREATE_PAGE"}
    elif capability == "modify":
        want["intents"] = (set(STOP) if expect.get("refuse")
                           else {"MODIFY_PAGE", "UNCLEAR"} if expect.get("ask") else {"MODIFY_PAGE"})
    elif expect.get("ask"):
        want["intents"] = set(STOP)
    else:
        want.update(intents={"WRITING"}, action=expect.get("action"), language=expect.get("language"))
    return want


def matches(answer: Any, want: dict[str, Any]) -> bool:
    if not isinstance(answer, dict) or answer.get("intent") not in want["intents"]:
        return False
    if want["action"] and answer.get("writingAction") != want["action"]:
        return False
    return not want["language"] or answer.get("language") == want["language"]


def parse_answer(text: str) -> dict[str, Any] | str:
    try:
        found = IntentExtraction.model_validate(parse_json_object(text))
    except (ValueError, TypeError):
        return "model_loi"
    return {"intent": found.intent, "writingAction": found.writingAction, "language": found.language}


class Recording:
    def __init__(self, provider: Any) -> None:
        self.provider = provider
        self.provider_name = provider.provider_name
        self.model_name = provider.model_name
        self.texts: list[str] = []

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        result = await self.provider.generate(*args, **kwargs)
        self.texts.append(result.text)
        return result


async def ask(provider: Any, request: IntentRequest) -> dict[str, Any] | str:
    system_prompt, user_prompt = build_intent_prompt(request)
    try:
        generated = await provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, max_new_tokens=200,
                                            response_schema=IntentExtraction.model_json_schema())
    except InvalidLLMResponseError:
        return "model_loi"
    return parse_answer(generated.text)


async def probe_case(capability: str, case: dict[str, Any], local: Any, others: dict[str, Any],
                     titles: list[str] | None = None, current: str | None = None) -> dict[str, Any]:
    want = expected(capability, case)
    request = IntentRequest(instruction=case["instruction"], selectedText=case.get("selectedText"),
                            currentPageId=current, pageTitles=titles or [])
    recorder = Recording(local)
    row: dict[str, Any] = {"id": case["id"], "group": case["group"], "capability": capability,
                           "instruction": case["instruction"]}
    try:
        final = (await IntentService(recorder).process(request)).result
        row["final"] = final.intent
        right = matches(final.model_dump(), want)
    except InvalidLLMResponseError:
        row["final"], right = "loi", False
    if right:
        row.update(who="dung", raw={}, rawRight={})
        return row
    normalized = request.model_copy(update={"instruction": normalize_edit_instruction(request.instruction)})
    if recorder.texts:
        raw_local = parse_answer(recorder.texts[-1])
        who = "loi" if row["final"] == "loi" else "cong_ha" if matches(raw_local, want) else "model_sai"
    else:
        raw_local, who = await ask(local, normalized), "luat_quyet"
    raw = {LOCAL: raw_local}
    for name, provider in others.items():
        raw[name] = await ask(provider, normalized)
    row.update(who=who, raw=raw, rawRight={name: matches(answer, want) for name, answer in raw.items()})
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for capability in dict.fromkeys(row["capability"] for row in rows):
        mine = [row for row in rows if row["capability"] == capability]
        stuck = [row for row in mine if row["who"] != "dung"]
        names = list(dict.fromkeys(name for row in stuck for name in row["rawRight"]))
        any_right = sum(any(row["rawRight"].values()) for row in stuck)
        summary[capability] = {
            "cases": len(mine), "stuck": len(stuck), **{who: sum(row["who"] == who for row in stuck) for who in WHO},
            "right": {name: sum(row["rawRight"].get(name, False) for row in stuck) for name in names},
            "rightAny": any_right, "share": round(any_right / len(stuck), 2) if stuck else 0.0,
        }
    return summary


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.llm.factory import create_gemini_provider
    from evaluation.natural_vi_generator import generate
    from scripts.evaluate_end_to_end import Metered, build_services, run_probe
    from scripts.evaluate_natural_vi import _sample_pages, split_bank

    check_split(args.split)
    bank, seed, _ = split_bank(args.split)
    sets = generate(bank, seed)
    config = get_settings()
    services = build_services(config)
    local = services.intents.llm_provider
    others = ({"gemini": Metered(create_gemini_provider(config), interval=args.gemini_interval)}
              if args.gemini else {})
    rows = []
    try:
        for capability in (args.only.split(",") if args.only else CAPABILITIES):
            cases = sets[capability]
            named, open_id = {}, None
            if capability == "modify":
                pages, open_id = _sample_pages(bank["modify"])
                named = run_probe(args.be, [{"id": case["id"], "kind": "titles", "instruction": case["instruction"],
                                             "pages": pages} for case in cases], quiet=True)
            print(f"[{capability}] {len(cases)} câu", flush=True)
            for case in cases:
                titles = (named.get(case["id"]) or {}).get("titles") or []
                rows.append(await probe_case(capability, case, local, others, titles,
                                             open_id if case.get("current") else None))
    finally:
        for provider in [*services.providers, *others.values()]:
            await provider.close()
    return {"split": args.split, "seed": seed, "local": f"{local.provider_name}:{local.model_name}",
            "others": {name: f"{item.provider_name}:{item.model_name}" for name, item in others.items()},
            "summary": summarize(rows), "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "dev2"], required=True)
    parser.add_argument("--be", type=Path, required=True)
    parser.add_argument("--only")
    parser.add_argument("--gemini", action="store_true")
    parser.add_argument("--gemini-interval", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(run(args))
    for capability, entry in report["summary"].items():
        print(f"{capability}: {json.dumps(entry, ensure_ascii=False)}")
    for row in report["rows"]:
        if row["who"] != "dung":
            print(f"{row['id']} {row['group']} final={row['final']} who={row['who']} raw={row['raw']} | {row['instruction']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
