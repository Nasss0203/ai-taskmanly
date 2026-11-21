"""Read-only M0 evaluation. No database access or capability execution.

Run with ``python -m scripts.evaluate_intent --mode rules-only``.
Replay mode consumes supplied provider responses, never the expected labels.
Only Ollama mode loads runtime settings and requires valid local configuration.
"""

import argparse
import asyncio
import json
from collections import deque
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.llm.base import LLMGenerationResult, LLMProvider
from app.modules.intent.schemas.intent_schema import IntentRequest
from app.modules.intent.services.intent_service import IntentService
from app.modules.page_intent.services.page_reference_evidence import detect_page_reference

DEFAULT_CASES = Path(__file__).resolve().parents[1] / 'evaluation' / 'intent_cases.jsonl'
SELECTION_FIXTURE = 'Taskmanly helps teams organize work and collaborate on project plans.'


class LLMRequired(Exception):
    pass


class EvaluationProvider:
    provider_name = 'evaluation-replay'
    model_name = 'supplied-responses'

    def __init__(self, mode: str, delegate: LLMProvider | None = None):
        self.mode = mode
        self.delegate = delegate
        self.responses: deque[str] = deque()
        self.calls = 0

    async def generate(self, **kwargs) -> LLMGenerationResult:
        if self.mode == 'rules-only':
            raise LLMRequired()
        self.calls += 1
        if self.delegate is not None:
            return await self.delegate.generate(**kwargs)
        if not self.responses:
            raise LLMRequired()
        return LLMGenerationResult(text=self.responses.popleft())


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    identifiers = set()
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or not isinstance(record.get('id'), str):
                raise ValueError()
            if not isinstance(record.get('text'), str) or not isinstance(record.get('intent'), str):
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Invalid case structure at line {number}.') from exc
        if record['id'] in identifiers:
            raise ValueError(f'Duplicate case ID at line {number}.')
        identifiers.add(record['id'])
        cases.append(record)
    return cases


def request_for_case(case: dict[str, Any]) -> IntentRequest:
    selection = case.get('selectedText')
    if selection is None and case.get('selection'):
        selection = SELECTION_FIXTURE
    current_page = case.get('currentPageId')
    if current_page is None and case.get('open_page'):
        current_page = 'evaluation-current-page'
    return IntentRequest(instruction=case['text'], selectedText=selection, currentPageId=current_page)


def _group() -> dict[str, Any]:
    return {'eligible': 0, 'correct': 0, 'accuracy': None, 'llmRequired': 0, 'errors': 0,
            'referenceEligible': 0, 'referenceCorrect': 0}


async def evaluate_cases(
    cases: list[dict[str, Any]], *, mode: str = 'rules-only',
    replays: dict[str, list[str]] | None = None, provider: LLMProvider | None = None,
) -> dict[str, Any]:
    if mode not in {'rules-only', 'replay', 'ollama'}:
        raise ValueError('Unsupported evaluation mode.')
    if mode == 'ollama' and (provider is None or provider.provider_name != 'ollama'):
        raise ValueError('Ollama mode requires a real Ollama provider.')
    capture = EvaluationProvider(mode, provider)
    if provider is not None:
        capture.provider_name, capture.model_name = provider.provider_name, provider.model_name
    service = IntentService(capture)
    report: dict[str, Any] = {
        'mode': mode, 'total': len(cases), 'eligible': 0, 'correct': 0, 'invalid': 0, 'invalidRejected': 0,
        'tbd': 0, 'llmRequired': 0, 'llmCalls': 0, 'errors': 0, 'mutationFalsePositives': 0,
        'realModelRun': False, 'm0ThresholdSatisfied': False,
        'referenceSource': 'deterministic-page-reference-evidence', 'groups': {}, 'cases': [],
    }
    by_intent: dict[str, dict[str, Any]] = {}
    for case in cases:
        expected = case['intent']
        # Reports contain IDs and finite contract labels, never source/selection
        # text, provider responses or exception messages.
        row = {'id': case['id'], 'expectedIntent': expected, 'expectedAction': case.get('action')}
        report['cases'].append(row)
        if any(case.get(field) == 'TBD' for field in ('intent', 'action', 'language', 'reference')):
            report['tbd'] += 1
            row['status'] = 'TBD_EXCLUDED'
            continue
        try:
            request = request_for_case(case)
        except ValidationError:
            if expected == 'INVALID':
                report['invalid'] += 1
                report['invalidRejected'] += 1
                row['status'] = 'INVALID_REJECTED'
                continue
            request = None
        if expected == 'INVALID':
            report['invalid'] += 1
            row['status'] = 'INVALID_NOT_REJECTED'
            continue
        group = report['groups'].setdefault(case.get('group', expected), _group())
        intent_group = by_intent.setdefault(expected, _group())
        for counter in (report, group, intent_group):
            counter['eligible'] += 1
        if request is None:
            row['status'] = 'UNEXPECTED_INPUT_REJECTION'
            report['errors'] += 1
            group['errors'] += 1
            intent_group['errors'] += 1
            continue
        if case.get('reference'):
            evidence = detect_page_reference(
                request.instruction, has_current_page=bool(request.currentPageId),
            )
            actual_reference = evidence.reference_type
            row.update(expectedReference=case['reference'], actualReference=actual_reference)
            reference_correct = actual_reference == case['reference']
            if 'pageReference' in case:
                row['pageReferenceMatches'] = evidence.title == case['pageReference']
                reference_correct = reference_correct and row['pageReferenceMatches']
            group['referenceEligible'] += 1
            group['referenceCorrect'] += int(reference_correct)
        capture.responses = deque((replays or {}).get(case['id'], []))
        try:
            response = await service.process(request)
            actual = response.result
            row.update(actualIntent=actual.intent, actualAction=actual.writingAction,
                       actualLanguage=actual.language, needsClarification=actual.needsClarification,
                       path='deterministic' if response.provider == 'deterministic' else 'llm')
            correct = actual.intent == expected and actual.writingAction == case.get('action')
            if case.get('language') is not None:
                correct = correct and actual.language == case['language']
            row['status'] = 'MATCH' if correct else 'MISMATCH'
            for counter in (report, group, intent_group):
                counter['correct'] += int(correct)
            if expected not in {'CREATE_PAGE', 'MODIFY_PAGE'} and actual.intent in {'CREATE_PAGE', 'MODIFY_PAGE'}:
                report['mutationFalsePositives'] += 1
        except LLMRequired:
            row['status'] = 'LLM_REQUIRED'
            report['llmRequired'] += 1
            group['llmRequired'] += 1
            intent_group['llmRequired'] += 1
        except Exception as exc:
            row.update(status='ERROR', errorType=type(exc).__name__)
            report['errors'] += 1
            group['errors'] += 1
            intent_group['errors'] += 1
    report['llmCalls'] = capture.calls
    report['realModelRun'] = mode == 'ollama' and capture.calls > 0
    for counter in [report, *report['groups'].values(), *by_intent.values()]:
        counter['accuracy'] = counter['correct'] / counter['eligible'] if counter['eligible'] else None
    report['byIntent'] = by_intent
    report['m0ThresholdSatisfied'] = bool(
        report['realModelRun'] and report['invalid'] == report['invalidRejected']
        and not report['errors'] and not report['llmRequired'] and not report['mutationFalsePositives']
        and all(by_intent.get(label, {}).get('accuracy', 0) >= .95
                for label in ('CREATE_PAGE', 'MODIFY_PAGE', 'WRITING'))
    )
    return report


async def main(args: argparse.Namespace) -> int:
    provider = None
    try:
        cases = load_cases(args.cases)
        replays = json.loads(args.replay.read_text(encoding='utf-8')) if args.replay else None
        if args.mode == 'ollama':
            from app.core.config import get_settings
            from app.llm.providers.ollama import OllamaProvider

            config = get_settings()  # Do not bypass token validation for runtime development.
            provider = OllamaProvider(
                base_url=config.ollama_base_url, model_name=config.ollama_model,
                timeout_seconds=config.ollama_timeout_seconds, num_ctx=config.ollama_num_ctx,
                num_gpu=config.ollama_num_gpu,
            )
        report = await evaluate_cases(cases, mode=args.mode, replays=replays, provider=provider)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        summary = {key: value for key, value in report.items() if key != 'cases'}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if report['correct'] == report['eligible'] and report['invalid'] == report['invalidRejected'] else 1
    except Exception as exc:
        # Settings and provider exceptions can include secrets or private data.
        print(json.dumps({'status': 'EVALUATION_FAILED', 'errorType': type(exc).__name__}))
        return 2
    finally:
        if provider is not None:
            await provider.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    parser.add_argument('--mode', choices=['rules-only', 'replay', 'ollama'], default='rules-only')
    parser.add_argument('--replay', type=Path, help='Mapping of case ID to list of raw provider response strings.')
    parser.add_argument('--output', type=Path)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
