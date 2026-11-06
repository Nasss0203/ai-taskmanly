"""Bound AI inputs without truncating instructions or context.

The 10000-byte user input budget is chosen against the default 16384-token
window and generation budgets (1000 Writing, 4000 Composition, 1200 Planner).
It reserves headroom for system prompts and schemas; it is a resource ceiling,
not exact tokenizer accounting or a guarantee for smaller custom windows.
"""

import json
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field


MAX_INSTRUCTION_LENGTH = 4000
MAX_WRITING_LENGTH = 8000
MAX_INPUT_BYTES = 10000
MAX_CONTEXT_BYTES = 8000
MAX_CONTEXT_DEPTH = 12
MAX_CONTEXT_NODES = 1000
MAX_BODY_BYTES = 65536
MAX_JSON_DEPTH = MAX_CONTEXT_DEPTH + 1  # request wrapper
# Kế hoạch trang dài (E3): a Page's own context for the planner (≤ 200 blocks in
# NestJS). Each text stays ≤ MAX_CONTEXT_BYTES; the prompt gets only what fits
# its token budget (context_window.py). Below MAX_BODY_BYTES with references.
MAX_PAGE_CONTEXT_BYTES = 56000
MAX_PAGE_CONTEXT_NODES = 8000
MAX_PAGE_INPUT_BYTES = 58000


def require_non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must not be blank.")
    return value


def validate_input_budget(value: Any) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("Combined AI input exceeds the 10000-byte UTF-8 budget.")
    return value


def _bounded_context(value: Any, max_bytes: int, max_nodes: int) -> Any:
    if value is None:
        return value
    original = value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")

    # Bound traversal before serialization or nested Pydantic validation.
    stack = [(value, 1)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise ValueError(f"Context exceeds the {max_nodes}-node limit.")
        if isinstance(item, (dict, list, tuple)):
            if depth > MAX_CONTEXT_DEPTH:
                raise ValueError("Context exceeds the 12-level nesting limit.")
            if len(item) > max_nodes:
                raise ValueError(f"Context exceeds the {max_nodes}-node limit.")
            if isinstance(item, dict):
                for key in item:
                    if not isinstance(key, str) or len(key) > MAX_CONTEXT_BYTES:
                        raise ValueError("Context contains an invalid or oversized key.")
                children = item.values()
            else:
                children = item
            stack.extend((child, depth + 1) for child in children)
        elif isinstance(item, str) and len(item) > MAX_CONTEXT_BYTES:
            raise ValueError(f"Context exceeds the {MAX_CONTEXT_BYTES}-byte UTF-8 limit.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Context must contain bounded JSON data.") from exc
    if len(encoded) > max_bytes:
        raise ValueError(f"Context exceeds the {max_bytes}-byte UTF-8 limit.")
    return original


def validate_context(value: Any) -> Any:
    return _bounded_context(value, MAX_CONTEXT_BYTES, MAX_CONTEXT_NODES)


def validate_page_context(value: Any) -> Any:
    """A Page's own context for the planner (kế hoạch trang dài, E3)."""
    return _bounded_context(value, MAX_PAGE_CONTEXT_BYTES, MAX_PAGE_CONTEXT_NODES)


def validate_page_input_budget(value: Any, max_bytes: int = MAX_PAGE_INPUT_BYTES) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError(f"Combined AI input exceeds the {max_bytes}-byte UTF-8 budget.")
    return value


Instruction = Annotated[
    str,
    Field(min_length=1, max_length=MAX_INSTRUCTION_LENGTH),
    AfterValidator(require_non_blank),
]
WritingText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_WRITING_LENGTH),
    AfterValidator(require_non_blank),
    AfterValidator(validate_input_budget),
]
BoundedContext = Annotated[dict[str, Any], BeforeValidator(validate_context)]
CurrentPageId = Annotated[
    str,
    Field(min_length=1, max_length=128),
    AfterValidator(require_non_blank),
]
