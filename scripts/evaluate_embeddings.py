"""M5 (kế hoạch hạ tầng vector, F2): which embedding model finds Pages better.

Each Page gets one vector for its title and headers (M6) and one per block
(M7); a Page scores its best vector. Counts how often the right Page is in
the top 3 / first, per model. Calls the local Ollama; no database.

Run with ``python -m scripts.evaluate_embeddings qwen3-embedding:0.6b bge-m3``.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter

from app.llm.providers.ollama_embedding import OllamaEmbeddingProvider
from app.modules.embedding.schemas.embedding_schema import EmbeddingRequest
from app.modules.embedding.services.embedding_service import EmbeddingService

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evaluation" / "embedding_cases.json"


def page_texts(page: dict) -> list[tuple[str, str]]:
    """(page id, text) rows, the way NestJS will build them (F4)."""
    rows = [(page["id"], "\n".join([page["title"], *page["headers"]]))]
    rows += [(page["id"], block) for block in page["blocks"]]
    return rows


async def evaluate(model: str, cases: dict, base_url: str, num_gpu: int | None) -> None:
    provider = OllamaEmbeddingProvider(base_url, model, 300, num_gpu=num_gpu)
    service = EmbeddingService(provider)
    try:
        rows = [row for page in cases["pages"] for row in page_texts(page)]
        started = perf_counter()
        documents = []
        for start in range(0, len(rows), 32):
            batch = [text for _, text in rows[start:start + 32]]
            response = await service.process(EmbeddingRequest(kind="document", texts=batch))
            documents += response.embeddings
        document_seconds = perf_counter() - started

        top1 = top3 = 0
        misses = []
        query_seconds = 0.0
        for case in cases["queries"]:
            started = perf_counter()
            response = await service.process(EmbeddingRequest(kind="query", texts=[case["text"]]))
            query_seconds += perf_counter() - started
            query = response.embeddings[0]
            best: dict[str, float] = {}
            for (page_id, _), vector in zip(rows, documents):
                score = sum(a * b for a, b in zip(query, vector))
                best[page_id] = max(best.get(page_id, -1.0), score)
            ranking = sorted(best, key=best.get, reverse=True)
            top1 += ranking[0] == case["page"]
            top3 += case["page"] in ranking[:3]
            if ranking[0] != case["page"]:
                misses.append(f'  {case["kind"]:<11} "{case["text"]}" → {ranking[:3]} (want {case["page"]})')

        total = len(cases["queries"])
        print(
            f"{model}: top1 {top1}/{total}, top3 {top3}/{total}; "
            f"{len(rows)} texts in {document_seconds:.1f} s, "
            f"query {query_seconds / total * 1000:.0f} ms on average"
        )
        print("\n".join(misses))
    finally:
        await provider.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--num-gpu", type=int, default=0)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # arrows and Vietnamese on Windows
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    for model in args.models:
        asyncio.run(evaluate(model, cases, args.base_url, args.num_gpu))


if __name__ == "__main__":
    main()
