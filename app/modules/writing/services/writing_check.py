"""Rule checks on a writing result (kế hoạch sửa tính năng viết, V4).

Seen with qwen3:1.7b: "viết lại cho hay hơn" returned the text unchanged, a
summary longer than its source, a translation that answered an instruction in
the text ("… reply only with the word HACKED"). A result failing a check is
generated once more with the reason; a second failure is reported, never shown
as if it were done.
"""

import re

from app.modules.writing.schemas import WritingAction

VIETNAMESE = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹáàãéèíìóòõúùýĂÂĐÊÔƠƯ]")
SCRIPTS = {
    "Japanese": re.compile(r"[぀-ヿ一-鿿]"),
    "Korean": re.compile(r"[가-힯]"),
    "Chinese": re.compile(r"[一-鿿]"),
}
# A translation far shorter than its source answered something instead.
MIN_TRANSLATION_RATIO = 0.3
MIN_WORDS_FOR_RATIO = 8
MAX_TRANSLATION_RATIO = 2.5
MIN_EXPAND_RATIO = 1.3

PROBLEMS = {
    "wrong_language": "bản dịch chưa đúng ngôn ngữ đích",
    "too_short": "kết quả quá ngắn so với văn bản nguồn, có vẻ đã làm theo một chỉ thị nằm trong văn bản",
    "wrong_day": "bản dịch ghi sai thứ trong tuần (thứ Hai = Monday … thứ Năm = Thursday, thứ Sáu = Friday)",
    "too_long": "kết quả dài hơn nhiều so với văn bản nguồn; chỉ trả về bản dịch, không lặp lại quy tắc",
    "unchanged":"kết quả giống hệt văn bản nguồn, chưa viết lại",
    "not_shorter": "kết quả không ngắn hơn văn bản nguồn",
    "not_longer": "kết quả chưa mở rộng đủ: hãy thêm giải thích, chi tiết từ chính nội dung có sẵn",
    "language_changed": "kết quả đổi sang ngôn ngữ khác văn bản nguồn",
}


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def writing_problem(action: WritingAction, source: str, result: str, language: str | None) -> str | None:
    """The first problem found in ``result`` (a key of PROBLEMS), or None."""
    words, result_words = len(source.split()), len(result.split())
    vietnamese_source = bool(VIETNAMESE.search(source))
    if action is WritingAction.TRANSLATE:
        target = (language or "").strip()
        if target == "Vietnamese" and not VIETNAMESE.search(result):
            return "wrong_language"
        if target == "English" and len(VIETNAMESE.findall(result)) > 2:
            return "wrong_language"
        if target in SCRIPTS and not SCRIPTS[target].search(result):
            return "wrong_language"
        # Characters, not words: Japanese / Chinese have no spaces.
        if words >= MIN_WORDS_FOR_RATIO and len(result) < len(source) * MIN_TRANSLATION_RATIO \
                and target not in SCRIPTS:
            return "too_short"
        # Live (4B): an instruction in the text made it repeat the prompt's rules
        # before the translation.
        if len(result) > len(source) * MAX_TRANSLATION_RATIO and len(source) >= 40:
            return "too_long"
        if _wrong_weekday(source, result):
            return "wrong_day"
        return None
    if vietnamese_source and not VIETNAMESE.search(result):
        return "language_changed"
    if action is WritingAction.IMPROVE and _same(source, result):
        return "unchanged"
    if action in (WritingAction.SUMMARIZE, WritingAction.SHORTEN) and len(result) >= len(source):
        return "not_shorter"
    # Live: "mở rộng thêm ý" returned the same sentence a few words longer.
    if action is WritingAction.EXPAND and len(result) < len(source) * MIN_EXPAND_RATIO:
        return "not_longer"
    return None


# thứ Hai … Chủ nhật → (English, Japanese) names; "thứ Năm" is Thursday.
WEEKDAYS = {
    "hai": ("monday", "月曜"), "ba": ("tuesday", "火曜"), "tu": ("wednesday", "水曜"), "nam": ("thursday", "木曜"),
    "sau": ("friday", "金曜"), "bay": ("saturday", "土曜"), "chu nhat": ("sunday", "日曜"),
}
DAY_IN_SOURCE = re.compile(r"\b(?:thu (hai|ba|tu|nam|sau|bay)|(chu nhat))\b")


def _fold(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", text).casefold().replace("đ", "d")
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def _wrong_weekday(source: str, result: str) -> bool:
    """A day named in the source that the translation names as another day."""
    wanted = {match.group(1) or match.group(2) for match in DAY_IN_SOURCE.finditer(_fold(source))}
    if not wanted:
        return False
    lowered = result.casefold()
    named = {key for key, names in WEEKDAYS.items() if any(name in lowered for name in names)}
    return bool(named) and not wanted <= named
