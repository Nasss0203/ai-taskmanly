"""A new Page's tables as the user asked for them (kế hoạch thử chat + viết, lỗi bảng).

Live: "Tạo trang Thử bảng AI có bảng Tasks gồm cột Tên, Trạng thái (Todo, Done)"
was drafted with a database but no DATABASE_VIEW block — the table was created
and never shown, so later "thêm dòng vào bảng Tasks" found no table — with the
columns renamed "Name / Status", and with TEXT lines "Tên", "Trạng thái",
"Todo", "Done" standing for the columns. Fixed deterministically:

- every database gets one DATABASE_VIEW block (after the page's opening blocks);
- columns the sentence names ("cột A, B (x, y), C") keep the user's words when
  their count equals the drafted properties (in order), options likewise;
- lines that only repeat a column, option or table name are dropped.
"""

import re
import unicodedata

from app.modules.modification_planner.services.sentence_text import text_key
from app.modules.page_composition.schemas.page_composition_schema import PageCompositionDraft

COLUMNS = re.compile(r"\b(?:cột|cot|columns?)\s*:?\s*(?P<list>.+)$", re.IGNORECASE)
OPTIONS = re.compile(r"\(([^()]*)\)")
GROUPED_OPTIONS = re.compile(r"\s+(?:bao gồm|bao gom|gồm|gom)\s+(?P<items>[^\x00]+)$", re.IGNORECASE)
TABLE_PAGE = re.compile(
    r"^(?:tạo|tao|lập|lap|(?:tôi|toi|mình|minh|em)\s+(?:cần|can|muốn|muon)(?:\s+(?:tạo|tao))?)\s+"
    r"(?:(?:một|mot|mới|moi)\s+)*trang\s+(?P<title>[^,:]+?)\s+"
    r"(?:có|co|với|voi)\s+(?:(?:một|mot)\s+)?(?:bảng|bang)\b\s*(?P<table>[^,:]*?)\s*"
    r"(?:(?:với|voi|gồm|gom|có|co)\s+)?(?:(?:các|cac)\s+)?(?:cột|cot)\b",
    re.IGNORECASE,
)
DATE_COLUMN = re.compile(r"\b(?:ngay|han|date|deadline|due)\b")
NUMBER_COLUMN = re.compile(
    r"\b(?:so tien|thanh tien|chi phi|gia tien|don gia|so luong|amount|price|cost|quantity|qty)\b",
)
SPLIT = re.compile(r"\s*,\s*|\s+(?:và|and)\s+", re.IGNORECASE)
ROW_REQUEST = re.compile(
    r"\b(?:dòng|bản ghi|dữ liệu mẫu|rows?|records?|sample)\b|\b(?:các|những|\d+)\s+(?:dong|ban ghi)\b",
    re.IGNORECASE,
)
TABLE_WORD = re.compile(r"\b(?:bảng|bang|database|cơ sở dữ liệu|table)\b", re.IGNORECASE)
TASK_REQUEST = re.compile(
    r"\b(?:gồm|gom|bao gồm|checklist|to-?do|việc|viec|nhiệm vụ|nhiem vu|tasks?|kế hoạch|ke hoach|plan)\b|:",
    re.IGNORECASE,
)
STRUCTURE_WORD = re.compile(r"\b(?:cot|columns?)\b")
CONTENT_REQUEST = re.compile(r"\b(?:gồm|gom|bao gồm|bao gom)\b|[:,]", re.IGNORECASE)
LISTED_CONTENT = re.compile(r"\b(?:checklist|check list|to-?dos?|việc cần làm|viec can lam)\b", re.IGNORECASE)
ECHO = r"(?:(?:tao|them|lap|create|add|make)\s+)?(?:(?:mot|a|an|the|new)\s+)?(?:bang|table|database)\s+"


def _named(name: str, key: str) -> bool:
    name_key = text_key(name)
    return bool(name_key) and re.search(rf"(?<!\w){re.escape(name_key)}(?!\w)", key) is not None


def _describes_table(text: str, columns: list[str], options: list[str]) -> bool:
    key = text_key(text)
    if STRUCTURE_WORD.search(key):
        return True
    if sum(_named(column, key) for column in columns) >= 2:
        return True
    return bool(re.search(r"\bco the la\b", key)) and any(_named(option, key) for option in options)


def _named_columns(instruction: str) -> list[tuple[str, list[str]]] | None:
    """[(column, options)] the sentence lists after "cột / columns", or None."""
    match = COLUMNS.search(unicodedata.normalize("NFC", instruction))
    if match is None:
        return None
    text = match.group("list").strip(" .")
    options: list[list[str]] = []

    def keep(found: re.Match[str]) -> str:
        options.append([item.strip() for item in SPLIT.split(found.group(1)) if item.strip()])
        return f"\x00{len(options) - 1}\x00"

    hidden = OPTIONS.sub(keep, text)
    grouped = GROUPED_OPTIONS.search(hidden)
    if grouped:
        options.append([item.strip() for item in SPLIT.split(grouped.group("items")) if item.strip()])
        hidden = f"{hidden[:grouped.start()]}\x00{len(options) - 1}\x00"
    columns = []
    for part in SPLIT.split(hidden):
        marker = re.search(r"\x00(\d+)\x00", part)
        name = re.sub(r"\x00\d+\x00", "", part).strip()
        if not name:
            return None
        columns.append((name[:1].upper() + name[1:], options[int(marker.group(1))] if marker else []))
    return columns or None


def _column_type(index: int, name: str, options: list[str]) -> str:
    if index == 0:
        return "TITLE"
    if options:
        return "SELECT"
    key = text_key(name)
    if DATE_COLUMN.search(key):
        return "DATE"
    if NUMBER_COLUMN.search(key):
        return "NUMBER"
    return "TEXT"


def compose_table_page(instruction: str) -> PageCompositionDraft | None:
    sentence = unicodedata.normalize("NFC", instruction).strip()
    match = TABLE_PAGE.match(sentence)
    if match is None or ROW_REQUEST.search(sentence) or LISTED_CONTENT.search(sentence[:match.end()]):
        return None
    title = match.group("title").strip(" .")
    if CONTENT_REQUEST.search(title) or TABLE_WORD.search(title):
        return None
    columns = _named_columns(sentence)
    if not columns or any(":" in name for name, _ in columns):
        return None
    table = match.group("table").strip(" .") or "Bảng"
    properties = [{
        "ref": f"p{index}", "name": name, "type": _column_type(index, name, options),
        **({"options": [{"ref": f"p{index}o{at}", "name": option} for at, option in enumerate(options)]}
           if options and index else {}),
    } for index, (name, options) in enumerate(columns)]
    title = title[:1].upper() + title[1:]
    return PageCompositionDraft.model_validate({
        "schemaVersion": 1, "type": "PAGE_COMPOSITION", "page": {"title": title},
        "blocks": [
            {"ref": "h0", "type": "HEADER", "content": {"text": title}, "styleConfig": {"level": 1}},
            {"ref": "view_block_db", "type": "DATABASE_VIEW", "databaseRef": "db", "viewRef": "v"},
        ],
        "databases": [{"ref": "db", "name": table[:1].upper() + table[1:], "properties": properties,
                       "views": [{"ref": "v", "name": "Bảng", "type": "TABLE"}], "rows": []}],
    })


def complete_databases(draft: PageCompositionDraft, instruction: str) -> PageCompositionDraft:
    if not draft.databases:
        return draft
    data = draft.model_dump(mode="json", exclude_none=True)
    changed = False

    columns = _named_columns(instruction)
    if columns and len(data["databases"]) == 1:
        properties = data["databases"][0]["properties"]
        if len(properties) == len(columns):
            for prop, (name, options) in zip(properties, columns):
                if prop["name"] != name:
                    prop["name"], changed = name, True
                drafted = prop.get("options") or []
                if options and len(drafted) == len(options):
                    for option, wanted in zip(drafted, options):
                        if option["name"] != wanted:
                            option["name"], changed = wanted, True

    # Lines that only name a column, an option or the table itself.
    names = {text_key(db["name"]) for db in data["databases"]}
    for db in data["databases"]:
        for prop in db["properties"]:
            names.add(text_key(prop["name"]))
            names.update(text_key(option["name"]) for option in prop.get("options") or [])
    names.update(text_key(f"bảng {db['name']}") for db in data["databases"])
    kept = [block for block in data["blocks"]
            if not (block["type"] in ("TEXT", "TODO") and text_key((block.get("content") or {}).get("text", "")) in names)]
    if len(kept) != len(data["blocks"]):
        data["blocks"], changed = kept, True

    sentence = unicodedata.normalize("NFC", instruction)
    if not ROW_REQUEST.search(sentence):
        for db in data["databases"]:
            if db.get("rows"):
                db["rows"], changed = [], True
    table_at = TABLE_WORD.search(sentence)
    only_table = table_at is not None and not TASK_REQUEST.search(sentence[:table_at.start()])
    listed_columns = COLUMNS.search(sentence)
    nothing_else = (table_at is not None and not CONTENT_REQUEST.search(sentence[:table_at.start()])
                    and not LISTED_CONTENT.search(sentence[:listed_columns.start()] if listed_columns else sentence))
    column_names = [prop["name"] for db in data["databases"] for prop in db["properties"]]
    option_names = [option["name"] for db in data["databases"] for prop in db["properties"]
                    for option in prop.get("options") or []]
    echoes = [re.compile(rf"^{ECHO}{re.escape(text_key(db['name']))}$") for db in data["databases"] if text_key(db["name"])]
    title_at = next((i for i, block in enumerate(data["blocks"]) if block["type"] == "HEADER"), None)
    kept = [block for index, block in enumerate(data["blocks"])
            if not (nothing_else and block["type"] != "DATABASE_VIEW" and index != title_at)
            and not (only_table and block["type"] == "TODO")
            and not (block["type"] in ("TEXT", "HEADER", "TODO")
                     and any(echo.match(text_key((block.get("content") or {}).get("text", ""))) for echo in echoes))
            and not (block["type"] in ("TEXT", "HEADER")
                     and _describes_table((block.get("content") or {}).get("text", ""), column_names, option_names))]
    if len(kept) != len(data["blocks"]):
        data["blocks"], changed = kept, True

    shown = {block.get("databaseRef") for block in data["blocks"] if block["type"] == "DATABASE_VIEW"}
    for db in data["databases"]:
        if db["ref"] in shown or not db.get("views"):
            continue
        view = {"ref": f"view_block_{db['ref']}", "type": "DATABASE_VIEW",
                "databaseRef": db["ref"], "viewRef": db["views"][0]["ref"]}
        # After the heading and the first line of text, where a table is read.
        roots = [i for i, block in enumerate(data["blocks"]) if not block.get("parentRef")]
        at = roots[min(2, len(roots) - 1)] + 1 if roots else 0
        data["blocks"].insert(at, view)
        changed = True
    return PageCompositionDraft.model_validate(data) if changed else draft
