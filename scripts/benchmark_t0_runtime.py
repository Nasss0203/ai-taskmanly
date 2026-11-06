"""T0 runtime experiment: intent (LLM cases) interleaved with planner gp cases.

Compares model placements without touching .env, NestJS or any database:

    # current setup: intent qwen3:1.7b on CPU, planner qwen3:4b-instruct on GPU
    python -m scripts.benchmark_t0_runtime --intent-model qwen3:1.7b --intent-num-gpu 0 \
        --output training/outputs/t0-runtime-split.json
    # one model for both: only one copy is ever loaded
    python -m scripts.benchmark_t0_runtime --intent-model qwen3:4b-instruct --intent-num-gpu 99 \
        --output training/outputs/t0-runtime-shared.json

Calls run sequentially. VRAM (nvidia-smi) and loaded models (/api/ps) are sampled
in the background; a "switch" is a sample whose loaded-model set differs from the
previous non-empty one, i.e. a reload. Outputs never contain prompts or settings values.
"""

import argparse
import asyncio
import json
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any
from urllib.request import urlopen

from scripts.evaluate_generation import CONTEXTS, check_plan
from scripts.evaluate_generation import DEFAULT_CASES as GENERATION_CASES
from scripts.evaluate_intent import DEFAULT_CASES as INTENT_CASES
from scripts.evaluate_intent import request_for_case


class Sampler(threading.Thread):
    def __init__(self, base_url: str, interval: float) -> None:
        super().__init__(daemon=True)
        self.base_url = base_url.rstrip('/')
        self.interval = interval
        self.samples: list[dict[str, Any]] = []
        self.stopped = threading.Event()

    def run(self) -> None:
        while not self.stopped.is_set():
            sample: dict[str, Any] = {'t': round(time.perf_counter(), 2)}
            try:
                out = subprocess.run(
                    ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=5,
                ).stdout.split(',')
                sample['vramUsed'], sample['vramTotal'] = int(out[0]), int(out[1])
            except Exception:
                sample['vramError'] = True
            try:
                with urlopen(f'{self.base_url}/api/ps', timeout=5) as response:
                    models = json.loads(response.read())['models']
                sample['models'] = sorted(m['name'] for m in models)
                sample['modelsVram'] = sum(m.get('size_vram', 0) for m in models)
            except Exception:
                sample['psError'] = True
            self.samples.append(sample)
            self.stopped.wait(self.interval)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))], 3)


def timing(values: list[float]) -> dict[str, Any]:
    return {'n': len(values), 'mean': round(mean(values), 3) if values else None,
            'p50': round(median(values), 3) if values else None, 'p95': percentile(values, .95)}


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    vram = [s['vramUsed'] for s in samples if 'vramUsed' in s]
    loaded = [tuple(s['models']) for s in samples if 'models' in s]
    switches, previous = 0, None
    for models in loaded:
        if models and previous is not None and models != previous:
            switches += 1
        if models:
            previous = models
    total = next((s['vramTotal'] for s in samples if 'vramTotal' in s), None)
    return {
        'samples': len(samples),
        'errors': sum('vramError' in s or 'psError' in s for s in samples),
        'vramTotalMiB': total, 'vramPeakMiB': max(vram, default=None),
        'vramMinFreeMiB': (total - max(vram)) if total and vram else None,
        'loadedSets': {' + '.join(k) or '(none)': v for k, v in Counter(loaded).items()},
        'modelSwitches': switches,
    }


async def timed(call) -> tuple[Any, float, str | None]:
    started = time.perf_counter()
    try:
        return await call, round(time.perf_counter() - started, 3), None
    except Exception as exc:  # Error type only: messages may contain private values.
        return None, round(time.perf_counter() - started, 3), type(exc).__name__


async def main(args: argparse.Namespace) -> int:
    from app.core.config import get_settings
    from app.llm.providers.ollama import OllamaProvider
    from app.modules.intent.services.intent_service import IntentService
    from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest
    from app.modules.modification_planner.services.modification_planner_service import ModificationPlannerService

    config = get_settings()

    def provider(model: str, num_gpu: int) -> OllamaProvider:
        return OllamaProvider(base_url=config.ollama_base_url, model_name=model,
                              timeout_seconds=config.ollama_timeout_seconds,
                              num_ctx=config.ollama_num_ctx, num_gpu=num_gpu)

    planner_provider = provider(args.planner_model, args.planner_num_gpu)
    shared = (args.intent_model, args.intent_num_gpu) == (args.planner_model, args.planner_num_gpu)
    intent_provider = planner_provider if shared else provider(args.intent_model, args.intent_num_gpu)
    intent_service, planner_service = IntentService(intent_provider), ModificationPlannerService(planner_provider)

    intent_ids, planner_ids = args.intent_ids.split(','), args.planner_ids.split(',')
    def load(path: Path) -> dict[str, dict[str, Any]]:
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        return {row['id']: row for row in rows}

    intent_cases, planner_cases = load(INTENT_CASES), load(GENERATION_CASES)

    async def run_intent(case_id: str, phase: str) -> dict[str, Any]:
        case = intent_cases[case_id]
        response, seconds, error = await timed(intent_service.process(request_for_case(case)))
        row = {'kind': 'intent', 'phase': phase, 'id': case_id, 'seconds': seconds, 'error': error}
        if response is not None:
            row.update(ok=response.result.intent == case['intent'], viaLLM=response.provider != 'deterministic')
        return row

    async def run_planner(case_id: str, phase: str) -> dict[str, Any]:
        case = planner_cases[case_id]
        context = CONTEXTS[case['context']]
        response, seconds, error = await timed(planner_service.process(
            ModificationPlannerRequest(instruction=case['instruction'], context=context)))
        row = {'kind': 'planner', 'phase': phase, 'id': case_id, 'seconds': seconds, 'error': error}
        if response is not None:
            failed = check_plan(response.result.model_dump(mode='json'), case['expect'], context)
            row.update(ok=not failed, failed=failed)
        return row

    sampler = Sampler(config.ollama_base_url, args.sample_interval)
    sampler.start()
    calls: list[dict[str, Any]] = []
    try:
        calls.append(await run_intent(intent_ids[0], 'warmup'))
        calls.append(await run_planner(planner_ids[0], 'warmup'))
        step = 0
        for _ in range(args.rounds):
            for case_id in planner_ids:
                if step % args.intent_every == 0:
                    calls.append(await run_intent(intent_ids[(step // args.intent_every) % len(intent_ids)], 'measure'))
                calls.append(await run_planner(case_id, 'measure'))
                step += 1
                print(f"{calls[-1]['id']}: {'ok' if calls[-1].get('ok') else calls[-1]['error'] or 'fail'} "
                      f"({calls[-1]['seconds']}s)", flush=True)
    finally:
        sampler.stopped.set()
        sampler.join(timeout=10)
        await planner_provider.close()
        if not shared:
            await intent_provider.close()

    summary: dict[str, Any] = {
        'config': {'intentModel': args.intent_model, 'intentNumGpu': args.intent_num_gpu,
                   'plannerModel': args.planner_model, 'plannerNumGpu': args.planner_num_gpu,
                   'sharedProvider': shared, 'numCtx': config.ollama_num_ctx, 'rounds': args.rounds,
                   'intentEvery': args.intent_every},
        'resources': summarize_samples(sampler.samples),
    }
    for kind in ('intent', 'planner'):
        rows = [c for c in calls if c['kind'] == kind and c['phase'] == 'measure']
        summary[kind] = {
            'calls': len(rows), 'ok': sum(bool(r.get('ok')) for r in rows),
            'errors': dict(Counter(r['error'] for r in rows if r['error'])),
            'viaLLM': sum(bool(r.get('viaLLM')) for r in rows) if kind == 'intent' else None,
            'secondsAll': timing([r['seconds'] for r in rows]),
            'secondsOk': timing([r['seconds'] for r in rows if r.get('ok')]),
            'failing': dict(Counter(r['id'] for r in rows if not r.get('ok'))),
        }
    summary['warmup'] = [c for c in calls if c['phase'] == 'warmup']
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'summary': summary, 'calls': calls, 'samples': sampler.samples},
                                          ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--intent-model', default='qwen3:1.7b')
    parser.add_argument('--intent-num-gpu', type=int, default=0)
    parser.add_argument('--planner-model', default='qwen3:4b-instruct')
    parser.add_argument('--planner-num-gpu', type=int, default=99)
    parser.add_argument('--intent-ids', default='c04,c16,c17', help='Intent cases that need the LLM.')
    parser.add_argument('--planner-ids', default='gp01,gp02,gp03,gp04,gp05,gp06,gp07,gp08')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--intent-every', type=int, default=3, help='One intent call before every N planner calls.')
    parser.add_argument('--sample-interval', type=float, default=0.5)
    parser.add_argument('--output', type=Path)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
