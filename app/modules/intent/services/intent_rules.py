"""Conservative source evidence. No Page resolution and no execution routing."""

import re
import unicodedata

from app.shared.vi_vocabulary import pattern, words
from app.modules.intent.services.writing_source import inline_writing_text
from app.modules.intent.schemas.intent_schema import IntentRequest, IntentResult, WritingActionName
from app.modules.intent.services.page_question_rules import page_question
from app.modules.modification_planner.services.block_delete import parse_block_delete
from app.modules.modification_planner.services.block_text import parse_block_text
from app.modules.modification_planner.services.todo_status import parse_todo_status
from app.modules.page_intent.services.page_reference_evidence import (
    QUOTED_TEXT, activity_page_reference, content_page_reference, detect_page_reference,
    is_read_only_page_request,
    has_multiple_page_targets, mask_quoted_text, source_backed_edit_instruction,
)


PAGE_WORD = re.compile(r'(?<!\w)(?<!tinh )(?:page|trang)(?!\w)(?!\s+thai\b)(?!\s+trong(?:\s+hon\b|\s*(?:[,.!?]|$)))',
                       re.IGNORECASE)


def fold(text: str) -> str:
    text = unicodedata.normalize('NFD', text).casefold().replace('đ', 'd')
    return ''.join(char for char in text if unicodedata.category(char) != 'Mn')


# Folding merges words that differ only by marks: "đích" (goal), "táo"
# (apple) and "đội" (team) are not "dịch", "tạo" or "đổi". Such a word keeps
# a "_" so no command pattern matches it; unmarked words still match.
VERB_SPELLINGS = {
    'dich': ('dịch',), 'tao': ('tạo',), 'xoa': ('xoá', 'xóa'), 'sua': ('sửa',),
    'chinh': ('chỉnh',), 'doi': ('đổi',), 'bo': ('bỏ', 'bổ'), 'go': ('gỡ',),
    'thay': ('thay',), 'them': ('thêm',), 'chen': ('chèn',), 'tich': ('tích',),
}


def mark_other_words(source: str) -> str:
    def word(match: re.Match[str]) -> str:
        written = match.group().casefold()
        folded = fold(written)
        spellings = VERB_SPELLINGS.get(folded)
        return f'{folded}_' if spellings and written != folded and written not in spellings else match.group()
    return re.sub(r'\w+', word, unicodedata.normalize('NFC', source))


def command_text(source: str) -> str:
    text = fold(source).strip()
    return re.sub(rf'^(?:{pattern("lead")}\s+)+', '', text)


ACTION_PATTERNS: tuple[tuple[WritingActionName, str], ...] = (
    ('IMPROVE', rf'{pattern("write_improve")}|make (?:it|this) more formal'),
    ('SHORTEN', rf'{pattern("write_shorten")}|make (?:it|this) shorter'),
    ('EXPAND', rf'{pattern("write_expand")}|them vi du minh hoa cho doan nay'),
    ('SUMMARIZE', rf'{pattern("write_summarize")}|tl;dr|liet ke \d+ y chinh'),
    ('CONTINUE', pattern("write_continue")),
    ('TRANSLATE', rf'(?:{pattern("write_translate")})(?!\s+vu\b)|sang tieng|(?:english|japanese|korean|vietnamese|french) please'),
)
ACTION_REGEXES = tuple((action, re.compile(rf'^(?:{regex})\b')) for action, regex in ACTION_PATTERNS)
STYLE_OF = {word: action for action, group in (('IMPROVE', 'write_style_improve'), ('SHORTEN', 'write_style_shorten'),
                                               ('EXPAND', 'write_style_expand')) for word in words(group)}
STYLES = pattern('write_style_improve', 'write_style_shorten', 'write_style_expand')
STYLE = re.compile(rf'\b(?:cho\s+(?P<after>{STYLES})|(?P<before>{STYLES})\s+hon)\b')
POINTED = (rf'(?:{pattern("write_passage")}|{pattern("write_passage_head")}\s+'
           rf'{pattern("write_passage_pointer", "write_selection")})')
PASSAGE = re.compile(rf'\b{POINTED}\b')
PASSAGE_LEAD = re.compile(rf'^(?:{POINTED}|{pattern("write_before_verb")})\s*,?\s+')
GENERIC_FIX = re.compile(rf'^{pattern("write_generic_fix")}\b')
GENERIC_MAKE = re.compile(rf'^{pattern("write_generic_make")}\b')
CONVERT = re.compile(rf'^{pattern("write_convert")}\b')
CONTINUE_SOFT = re.compile(rf'^{pattern("write_continue_soft")}\b')
CONTINUE_MARK = pattern('write_continue_mark')
ADD_NEXT = re.compile(rf'^(?:viet them|viet|them)\s+(?:(?:mot vai|vai|mot)\s+)?(?:{pattern("write_passage_head")}\s+)?'
                      rf'{CONTINUE_MARK}\b')
ADD_THEN_NEXT = re.compile(rf'^(?:viet them|them)\b.*\b{CONTINUE_MARK}\b')
LANGUAGE_BEFORE = pattern('language_prep', 'language_noun')
WANT_LEAD = re.compile(rf'^(?:{pattern("want", "let_me")}\s+)+')
SHORT_LEAD = re.compile(rf'^{pattern("lead_short")}\s+')
RESTYLED_VERBS = {'viet lai', *words('write_generic_fix'), *words('write_generic_make')}
EDIT_COMMAND = re.compile(
    r'^(?:them|chen|sua|chinh|cap nhat|doi|xoa|bo sung|ghi|viet lai|rut gon|dich|chep|'
    r'add|insert|edit|update|remove|delete|modify|change|replace|rename|append|prepend|move|reorder|rewrite|shorten|translate|copy|'
    # Kế hoạch tích to-do: ticking and unticking existing to-dos.
    r'tich(?!\s+(?:hop|cuc)\b)|danh dau|bo tich|bo danh dau|hoan thanh|lam xong|'
    r'check(?!\s+list\b)|uncheck|mark|complete|finish)\b',
)
OTHER_ACTION = re.compile(
    r'^(?:gui|dang|xoa|chia se|luu|in ra|send|post|share|email|publish|save|delete)\b'
)
CREATE_COMMAND = re.compile(r'^(?:tao|create|make|new page|lap ke hoach|soan tai lieu)\b')
LANGUAGES = {
    'English': ('tieng anh', 'english'),
    'Vietnamese': ('tieng viet', 'vietnamese'),
    'Japanese': ('tieng nhat', 'japanese'),
    'Korean': ('tieng han', 'korean'),
    'French': ('tieng phap', 'french'),
    'German': ('tieng duc', 'german'),
    'Chinese': ('tieng trung', 'chinese'),
    'Spanish': ('tieng tay ban nha', 'spanish'),
}


def _style(text: str) -> WritingActionName | None:
    found = STYLE.search(text)
    if found is None:
        return None
    return STYLE_OF[re.sub(r'\s+', ' ', found.group('after') or found.group('before'))]


def _language_named(text: str) -> bool:
    aliases = '|'.join(alias for names in LANGUAGES.values() for alias in names)
    return bool(re.search(rf'\b{LANGUAGE_BEFORE}\s+(?:{aliases})\b', text))


def _verb_action(text: str) -> tuple[WritingActionName, str] | None:
    best = None
    for action, regex in ACTION_REGEXES:
        found = regex.match(text)
        if found and (best is None or found.end() > len(best[1])):
            best = (action, found.group())
    return best


def writing_action(source: str, *, soft: bool = False, selected: bool = False) -> WritingActionName | None:
    text = command_text(source)
    style, language = _style(text), _language_named(text)
    passage = selected or bool(PASSAGE.search(text))
    asked = WANT_LEAD.sub('', text)
    unled = SHORT_LEAD.sub('', asked)
    candidates = [text, asked, unled, PASSAGE_LEAD.sub('', PASSAGE_LEAD.sub('', unled))]
    if ',' in text:
        candidates.append(command_text(text.rsplit(',', 1)[1]))
    for candidate in candidates:
        if ADD_NEXT.match(candidate) and (passage or candidate.startswith('viet')):
            return 'CONTINUE'
        if (ADD_THEN_NEXT.match(candidate) or CONTINUE_SOFT.match(candidate)) and passage:
            return 'CONTINUE'
        found = _verb_action(candidate)
        if found:
            action, verb = found
            if verb in RESTYLED_VERBS and language:
                return 'TRANSLATE'
            if verb in RESTYLED_VERBS and style:
                return style
            return action
        if CONVERT.match(candidate) and language:
            return 'TRANSLATE'
        if GENERIC_FIX.match(candidate) and (style or passage):
            return 'TRANSLATE' if language else style or 'IMPROVE'
        if GENERIC_MAKE.match(candidate) and style:
            return style
    if language and re.match(rf'^{pattern("language_noun")}\s', asked):
        return 'TRANSLATE'
    if style and passage:
        return style
    if soft and re.search(r'\b(?:muot ma hon|trang trong hon|more formal|more fluent)\b', text):
        return 'IMPROVE'
    return None


def inline_source(source: str) -> str | None:
    if writing_action(source) is None:
        return None
    # A Page object is not source text, even when its title is quoted.
    if PAGE_WORD.search(mask_quoted_text(source).split(':', 1)[0]):
        return None
    if ':' in source:
        value = source.split(':', 1)[1].strip()
        return value if value else None
    quote = QUOTED_TEXT.search(source)
    if quote and not re.search(r'\b(?:sang|to)\s+(?:tieng\s+)?$', fold(source[:quote.start()]).strip()):
        return quote.group()[1:-1].strip() or None
    # Kế hoạch sửa tính năng viết (V2): no ":" or quotes ("dịch sang tiếng Anh chúc …").
    return None if quote else inline_writing_text(source)


def directive_text(source: str) -> str:
    # Inline and selected text are data. Neither may introduce a second action.
    if inline_source(source) and ':' in source:
        source = source.split(':', 1)[0]
    return command_text(mask_quoted_text(source))


def translation_language(source: str) -> str | None:
    text = directive_text(source)
    for canonical, aliases in LANGUAGES.items():
        for alias in aliases:
            if re.search(rf'\b{LANGUAGE_BEFORE}\s+{alias}\b', text) or re.fullmatch(rf'{alias}\s+please[.!?]*', text):
                return canonical
    return None


def result(intent: str, action: str | None = None, language: str | None = None,
           *, clarify: bool = False) -> IntentResult:
    return IntentResult(intent=intent, writingAction=action, language=language,
                        needsClarification=clarify or intent == 'UNCLEAR')


def is_read_only(source: str) -> bool:
    text = directive_text(source)
    return is_read_only_page_request(source) or bool(re.match(
        r'^(?:page la gi|trang la gi|cam on|chao\b|hello\b|hi\b|ban la ai|so sanh\b|cach dung\b|lam sao\b)', text,
    )) or bool(re.search(r'\b(?:co bao nhieu|la gi\?|how many)\b', text))


def is_page_summary(source: str) -> bool:
    text = directive_text(source)
    return bool(re.match(r'^(?:tom tat|summarize)\s+(?:(?:the|this|current)\s+)?(?:trang|page)\b', text))


def unsupported_request(source: str) -> bool:
    return bool(re.match(
        r'^(?:viet (?:mot )?doan (?:van|gioi thieu)|viet email|write (?:an? )?(?:email|paragraph)|'
        r'chuyen thanh gach dau dong|giai thich doan|explain\b|nhan ban\b|duplicate\b|'
        r'(?:xoa|delete|remove)\s+(?:toan bo\s+|all\s+)?workspace\b)',
        directive_text(source),
    ))


def unsafe_override(source: str) -> bool:
    return bool(re.search(
        r'\b(?:bo qua (?:moi |cac )?huong dan|bo qua huong dan truoc|ignore (?:all |previous )?instructions|return pageid)\b',
        directive_text(source),
    ))


def creation_evidence(source: str) -> bool:
    text = directive_text(source)
    planning = re.match(r'^len ke hoach\s+(.+)', text)
    if planning:
        subject = planning.group(1).strip()
        return (not subject.endswith('?') and not PAGE_WORD.search(subject)
                and not re.match(r'^(?:la gi|nhu the nao|co nghia|nghia la)\b', subject))
    if re.match(r'^lam cho (?:toi|minh) (?:mot|1) (?:trang|page)\b', text):
        return True
    if re.match(r'^(?:minh|toi) (?:can|muon) (?:co )?mot (?:trang|page)\b', text):
        return True
    if re.match(r'^(?:add|insert)\s+(?:(?:a|another)\s+)?new\s+page\b|^them\s+trang\s+moi\b', text):
        return True
    if re.match(r'^(?:lap ke hoach|soan tai lieu|new page)\b', text):
        return True
    if re.match(r'^(?:tao|create|make)\s+(?:(?:mot|1|a|an|new|moi)\s+)*(?:trang|page|database|template|trnag)\b', text):
        return True
    # English descriptions can precede "page", but an in/to/on target marks
    # content creation inside an existing Page, not creation of a new Page.
    return bool(re.match(r'^(?:create|make)\b.*\bpage\b', text)
                and not re.search(r'\b(?:in|to|on)\b', text.split('page', 1)[0]))


def edit_evidence(request: IntentRequest) -> bool:
    source = request.instruction
    evidence = detect_page_reference(source, has_current_page=bool(request.currentPageId))
    if source_backed_edit_instruction(source, evidence):
        return True
    # "gửi email xong rồi" names the to-do first; there is no leading verb.
    # "thay X bằng Y" and "bỏ / gỡ X" use verbs EDIT_COMMAND lacks.
    if (parse_todo_status(source) is not None or parse_block_text(source) is not None
            or parse_block_delete(source) is not None):
        return True
    # Support explicit accent-free commands without trusting model instructions.
    command = EDIT_COMMAND.match(directive_text(source))
    return bool(command and directive_text(source)[command.end():].strip())


def multiple_commands(source: str) -> bool:
    # "tích A và Đích đến": a name after "và" is not a command (VERB_SPELLINGS).
    text = directive_text(mark_other_words(source))
    markers = list(PAGE_WORD.finditer(text))
    if len(markers) > 1 and re.search(r'\b(?:va|and)\s+(?:trang|page)\b(?!\s+thai\b)', text):
        return True
    # A second quoted name joined to a Page target is another target, not
    # source text. Rename's "thành/to" remains a single target.
    if markers and not inline_source(source):
        quotes = list(QUOTED_TEXT.finditer(source))
        for first, second in zip(quotes, quotes[1:]):
            between = fold(source[first.end():second.start()]).strip()
            if (first.start() > markers[0].start()
                    and between in {',', 'va', 'and', ', va', ', and'}
                    and not source[second.end():].lstrip().startswith(':')):
                return True
    clauses = re.split(r'\s+(?:roi|sau do|then|and then|va|and)\s+|[;.]\s+(?=[a-z])', text)
    categories = []
    for clause in clauses:
        action = writing_action(clause)
        if action:
            categories.append(action)
        elif CREATE_COMMAND.match(clause):
            content_creation = re.match(
                r'^(?:tao|create)\s+(?:(?:mot|1|a|an|new)\s+)*(?:dong|hang|row|heading|block|checklist)\b', clause,
            )
            categories.append('EDIT' if content_creation else 'CREATE')
        elif EDIT_COMMAND.match(clause):
            categories.append('EDIT')
    if len(set(categories)) > 1:
        return True
    # Kế hoạch sửa tính năng viết: "dịch sang tiếng Anh rồi gửi email cho sếp" —
    # a second action after "rồi / sau đó / then" that AI does not do.
    if categories and any(OTHER_ACTION.match(clause)
                          for clause in re.split(r'\s+(?:roi|sau do|then|and then)\s+', text)[1:]):
        return True
    if (has_multiple_page_targets(source) and len(categories) > 1
            and not creation_evidence(source)):
        return True
    # Two different Writing operations stay unclear even with one source.
    return False


def deterministic_result(request: IntentRequest) -> IntentResult | None:
    source = request.instruction
    if unsafe_override(source) or multiple_commands(source):
        return result('UNCLEAR')
    # M7 (H1): "tìm trang có nói về X rồi thêm …" edits the Page it finds;
    # without an edit, "tìm …" stays a read-only request below.
    if content_page_reference(source) is not None or activity_page_reference(source) is not None:
        return result('MODIFY_PAGE')
    if not request.selectedText and not inline_source(source):
        question = page_question(source, has_current_page=bool(request.currentPageId))
        if question is not None and question.kind == 'MIXED':
            return result('UNCLEAR')
        if question is not None:
            return IntentResult(
                intent='PAGE_QUESTION', questionKind=question.kind,
                pageReference=question.page_reference, databaseReference=question.database_reference,
            )
    reads_selection = bool(request.selectedText) and writing_action(source, selected=True) is not None
    if is_page_summary(source) or unsupported_request(source) or (is_read_only(source) and not reads_selection):
        return result('OTHER')
    text = directive_text(source)
    has_page = bool(PAGE_WORD.search(text))
    # "tạo bản ghi xong rồi, trong trang X" ticks a to-do: decided before creation.
    if has_page and parse_todo_status(source) is not None:
        evidence = detect_page_reference(source, has_current_page=bool(request.currentPageId))
        missing_current = evidence.reference_type == 'CURRENT_PAGE' and not request.currentPageId
        return result('MODIFY_PAGE', clarify=missing_current or evidence.reference_type == 'UNRESOLVED')
    if creation_evidence(source) and CREATE_COMMAND.match(text):
        return result('CREATE_PAGE')
    action = writing_action(source, selected=bool(request.selectedText))
    if has_page and edit_evidence(request):
        evidence = detect_page_reference(source, has_current_page=bool(request.currentPageId))
        missing_current = evidence.reference_type == 'CURRENT_PAGE' and not request.currentPageId
        return result('MODIFY_PAGE', clarify=missing_current or evidence.reference_type == 'UNRESOLVED')
    if action:
        if request.selectedText or inline_source(source):
            language = translation_language(source) if action == 'TRANSLATE' else None
            if action == 'TRANSLATE' and language is None:
                return result('UNCLEAR')
            return result('WRITING', action, language)
        if request.currentPageId and edit_evidence(request):
            return result('MODIFY_PAGE')
        return result('UNCLEAR')
    if edit_evidence(request):
        return result('MODIFY_PAGE') if request.currentPageId else result('UNCLEAR')
    if text.strip(' .!?') in {'voi', 'giup toi voi', 'sua di', 'abc', '', '🙂', 'lam cho tot hon', 'ok', 'cai do', 'lam tiep di', 'them', 'nhu luc nay'}:
        return result('UNCLEAR')
    if VAGUE_POINTING.match(text.strip(' .!?')):
        return result('UNCLEAR')
    return None


# Log Ask 2026-10-31 (u13, u14): the whole request is a generic verb and a
# pointing word ("làm cái đó đi", "fix it"). What it points at is not in the
# request, open Page or not, so ask instead of letting the model guess OTHER.
VAGUE_POINTING = re.compile(
    r'^(?:(?:lam|xu ly|giai quyet|do|fix|handle)\s+)?(?:(?:cai|viec|chuyen|phan)\s+)?'
    r'(?:do|nay|kia|ay|no|vay|the|that|this|it)'
    rf'(?:\s+(?:{pattern("tail", "loose_tail")}|luon|ngay))*$'
)
