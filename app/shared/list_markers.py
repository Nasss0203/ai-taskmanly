"""Leading list markers ("1.", "2)", "-", "•") that models put in item text.

A TODO block is already one list item and its order is the block order, so a
marker in its text is noise ("1. 1. Gửi báo cáo" once rendered on a Page).
"""

import re

LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def has_list_marker(text: str) -> bool:
    return bool(LIST_MARKER.match(text))


def strip_list_marker(text: str) -> str:
    stripped = LIST_MARKER.sub("", text, count=1).strip()
    return stripped or text
