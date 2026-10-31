"""How steady Ollama is under the Ask mix on this machine.

Calls the running AI service the way Ask does: page intent (qwen3:1.7b), the
modification planner and writing continue (qwen3:4b-instruct, with their own
num_gpu settings), embeddings (CPU). Counts, from Ollama's own server.log, how
often a model was loaded, failed to load or evicted others, and reports errors
and latency per kind of call.

Run with ``python -m scripts.benchmark_ollama_stability --rounds 3``.
"""

import argparse
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter

import httpx

from app.core.config import get_settings
from tests.test_modification_planner_schema import make_context


SERVER_LOG = Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "server.log"
LOG_EVENTS = {
    "loads": "loading model via llama-server",
    "load failures": "Load failed",
    "OOM evictions": "evicting all other loaded models",
    "out of memory": "bad_alloc",
}

CALLS = [
    ("page-intent", "/internal/v1/page-intent",
     {"instruction": "add a QA checklist to the release plan page"}),
    ("planner", "/internal/v1/modification-planner",
     {"instruction": "thêm checklist gồm build, test, release", "context": make_context()}),
    ("continue", "/internal/v1/writing",
     {"action": "CONTINUE", "text": "Taskmanly giúp nhóm sắp xếp công việc mỗi tuần"}),
    ("embeddings", "/internal/v1/embeddings",
     {"kind": "query", "texts": ["ghi chú QA gần đây"]}),
    ("page-intent", "/internal/v1/page-intent",
     {"instruction": "add the error codes to the API notes page"}),
    ("planner", "/internal/v1/modification-planner",
     {"instruction": "thêm checklist gồm viết release notes, kiểm tra staging", "context": make_context()}),
]


def log_size() -> int:
    return SERVER_LOG.stat().st_size if SERVER_LOG.exists() else 0


def log_events(since: int) -> dict[str, int]:
    if not SERVER_LOG.exists():
        return {}
    with SERVER_LOG.open("rb") as log:
        log.seek(since)
        text = log.read().decode("utf-8", errors="replace")
    return {name: text.count(marker) for name, marker in LOG_EVENTS.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    # The token is read from the service's own settings and never printed.
    token = get_settings().ai_internal_token.get_secret_value()
    headers = {"X-Internal-Service-Token": token}
    start = log_size()
    timings: dict[str, list[float]] = {}
    errors: dict[str, int] = {}
    with httpx.Client(base_url=args.base_url, timeout=300, headers=headers) as client:
        for round_index in range(1, args.rounds + 1):
            for kind, path, body in CALLS:
                started = perf_counter()
                try:
                    status = client.post(path, json=body).status_code
                except httpx.HTTPError as error:
                    status = type(error).__name__
                seconds = perf_counter() - started
                ok = status == 200
                timings.setdefault(kind, []).append(seconds)
                if not ok:
                    errors[kind] = errors.get(kind, 0) + 1
                print(f"round {round_index}  {kind:<11} {status!s:<16} {seconds:6.1f}s", flush=True)

    print()
    for kind, values in timings.items():
        ordered = sorted(values)
        p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
        print(f"{kind:<11} calls={len(values)} errors={errors.get(kind, 0)} "
              f"median={statistics.median(values):.1f}s p95={p95:.1f}s")
    events = log_events(start)
    print("ollama:", ", ".join(f"{name}={count}" for name, count in events.items()) or "server.log not found")


if __name__ == "__main__":
    main()
