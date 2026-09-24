import json
from typing import Any


def parse_json_object(raw_text: str) -> dict[str, Any]:
    data = json.loads(raw_text)

    if not isinstance(data, dict):
        raise ValueError("Expected LLM response to be a JSON object.")

    return data
