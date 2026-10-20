"""Read-only manual semantic smoke test using a real local Ollama model.

Run: .venv\Scripts\python.exe -m scripts.smoke_page_intent_ollama
Optional: --model qwen3:4b-instruct
This script never touches the business database.
"""

import argparse
import asyncio
import json
from time import perf_counter

from app.core.config import get_settings
from app.llm.providers.ollama import OllamaProvider
from app.modules.page_intent.schemas.page_intent_schema import PageIntentRequest
from app.modules.page_intent.services.page_intent_service import PageIntentService


CASES = [
    (
        "Thêm heading Sprint Goal vào page Release 2.0",
        ("MODIFY_PAGE", "TITLE", "Release 2.0", "Thêm heading Sprint Goal", False),
    ),
    (
        "Thêm một heading Sprint Goal và checklist QA vào page Release 2.0",
        (
            "MODIFY_PAGE",
            "TITLE",
            "Release 2.0",
            "Thêm một heading Sprint Goal và checklist QA",
            False,
        ),
    ),
    (
        "Thêm checklist QA vào page này",
        ("MODIFY_PAGE", "CURRENT_PAGE", None, "Thêm checklist QA", False),
    ),
    (
        'Thêm checklist vào trang "Kế hoạch phát hành"',
        ("MODIFY_PAGE", "TITLE", "Kế hoạch phát hành", "Thêm checklist", False),
    ),
    (
        "Chỉnh heading trong trang Sprint Planning 2026",
        ("MODIFY_PAGE", "TITLE", "Sprint Planning 2026", "Chỉnh heading", False),
    ),
    (
        "Thêm checklist vào page tôi sửa hôm qua",
        ("MODIFY_PAGE", "UNRESOLVED", None, "Thêm checklist", True),
    ),
    (
        "Thêm checklist vào trang nói về OAuth",
        ("MODIFY_PAGE", "UNRESOLVED", None, "Thêm checklist", True),
    ),
    (
        "Thêm checklist vào trang Alpha hoặc trang Beta",
        ("MODIFY_PAGE", "UNRESOLVED", None, "Thêm checklist", True),
    ),
    (
        "Thêm checklist vào page",
        ("MODIFY_PAGE", "UNRESOLVED", None, "Thêm checklist", True),
    ),
    (
        "Tạo page Release 2.0",
        ("OTHER", "UNRESOLVED", None, None, False),
    ),
    (
        "Viết lại câu này cho ngắn gọn: chúng ta đang chuẩn bị release.",
        ("OTHER", "UNRESOLVED", None, None, False),
    ),
    (
        "Page là gì?",
        ("OTHER", "UNRESOLVED", None, None, False),
    ),
    (
        "Thêm checklist QA vào page Phase3 E2E Duplicate f54fda01c7",
        (
            "MODIFY_PAGE",
            "TITLE",
            "Phase3 E2E Duplicate f54fda01c7",
            "Thêm checklist QA",
            False,
        ),
    ),
]


class CapturingProvider:
    def __init__(self, delegate: OllamaProvider):
        self.delegate = delegate
        self.provider_name = delegate.provider_name
        self.model_name = delegate.model_name
        self.last_text = None

    async def generate(self, **kwargs):
        result = await self.delegate.generate(**kwargs)
        self.last_text = result.text
        return result


async def main(model_name: str | None) -> int:
    config = get_settings()
    model = model_name or config.ollama_model
    provider = OllamaProvider(
        base_url=config.ollama_base_url,
        model_name=model,
        timeout_seconds=config.ollama_timeout_seconds,
        num_ctx=config.ollama_num_ctx,
        num_gpu=config.ollama_num_gpu,
    )
    capture = CapturingProvider(provider)
    service = PageIntentService(capture)
    passed = 0
    try:
        print(f"Testing real Ollama model={model}, cases={len(CASES)}", flush=True)
        for i, (sentence, expected) in enumerate(CASES, 1):
            capture.last_text = None
            start = perf_counter()
            try:
                response = await service.process(PageIntentRequest(instruction=sentence))
                result = response.result
                actual = (
                    result.intent,
                    result.referenceType,
                    result.pageReference,
                    result.instruction,
                    result.needsClarification,
                )
                ok = actual == expected
                if ok:
                    passed += 1
                print(
                    f"[{i:02d}] {'PASS' if ok else 'MISMATCH'} {perf_counter()-start:.1f}s "
                    f"input={sentence!r}",
                    flush=True,
                )
                if not ok:
                    print(f"     expected={expected}", flush=True)
                    print(f"     actual  ={actual}", flush=True)
            except Exception as error:
                print(
                    f"[{i:02d}] ERROR {perf_counter()-start:.1f}s "
                    f"input={sentence!r}: {type(error).__name__}: {error}",
                    flush=True,
                )
                if capture.last_text is not None:
                    print(f"     raw={capture.last_text[:1000]}", flush=True)
    finally:
        await provider.close()
    print(f"RESULT {passed}/{len(CASES)} exact semantic matches", flush=True)
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.model)))
