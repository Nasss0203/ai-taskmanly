"""Conservative source evidence. No Page resolution and no execution routing."""

import re
import unicodedata

from app.modules.intent.schemas.intent_schema import IntentRequest, IntentResult, WritingActionName
from app.modules.page_intent.services.page_reference_evidence import (
    PAGE_MARKER, QUOTED_TEXT, detect_page_reference, is_read_only_page_request,
    has_multiple_page_targets, mask_quoted_text, source_backed_edit_instruction,
)


def fold(text: str) -> str:
    text = unicodedata.normalize('NFD', text).casefold().replace('đ', 'd')
    return ''.join(char for char in text if unicodedata.category(char) != 'Mn')


def command_text(source: str) -> str:
    text = fold(source).strip()
    return re.sub(
        r'^(?:(?:hay|vui long|giup toi|giup minh|ban hay|please|can you|could you|would you)\s+)+',
        '', text,
    )


ACTION_PATTERNS: tuple[tuple[WritingActionName, str], ...] = (
    ('IMPROVE', r'viet lai|sua cau|sua loi chinh ta|viet chuyen nghiep hon|kiem tra ngu phap|make (?:it|this) more formal|paraphrase|rewrite|improve'),
    ('SHORTEN', r'rut gon|viet ngan lai|ngan gon|make (?:it|this) shorter|shorten'),
    ('EXPAND', r'viet dai hon|chi tiet hon|them vi du minh hoa cho doan nay|elaborate|expand'),
    ('SUMMARIZE', r'tom tat|tom lai y chinh|tl;dr|liet ke \d+ y chinh|summarize'),
    ('CONTINUE', r'viet tiep|continue'),
    ('TRANSLATE', r'dich|translate|sang tieng|(?:english|japanese|korean|vietnamese|french) please'),
)
EDIT_COMMAND = re.compile(
    r'^(?:them|chen|sua|chinh|cap nhat|doi|xoa|bo sung|ghi|viet lai|rut gon|dich|chep|'
    r'add|insert|edit|update|remove|delete|modify|change|replace|rename|append|prepend|move|reorder|rewrite|shorten|translate|copy)\b',
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


def writing_action(source: str, *, soft: bool = False) -> WritingActionName | None:
    text = command_text(source)
    for action, pattern in ACTION_PATTERNS:
        if re.match(rf'^(?:{pattern})\b', text):
            return action
    if soft and re.search(r'\b(?:muot ma hon|trang trong hon|more formal|more fluent)\b', text):
        return 'IMPROVE'
    return None


def inline_source(source: str) -> str | None:
    if writing_action(source) is None:
        return None
    # A Page object is not source text, even when its title is quoted.
    if PAGE_MARKER.search(mask_quoted_text(source).split(':', 1)[0]):
        return None
    if ':' in source:
        value = source.split(':', 1)[1].strip()
        return value if value else None
    quote = QUOTED_TEXT.search(source)
    if quote and not re.search(r'\b(?:sang|to)\s+(?:tieng\s+)?$', fold(source[:quote.start()]).strip()):
        return quote.group()[1:-1].strip() or None
    return None


def directive_text(source: str) -> str:
    # Inline and selected text are data. Neither may introduce a second action.
    if inline_source(source) and ':' in source:
        source = source.split(':', 1)[0]
    return command_text(mask_quoted_text(source))


def translation_language(source: str) -> str | None:
    text = directive_text(source)
    for canonical, aliases in LANGUAGES.items():
        for alias in aliases:
            if re.search(rf'\b(?:sang\s+|to\s+){alias}\b', text) or re.fullmatch(rf'{alias}\s+please[.!?]*', text):
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
        return (not subject.endswith('?') and not PAGE_MARKER.search(subject)
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
    # Support explicit accent-free commands without trusting model instructions.
    command = EDIT_COMMAND.match(directive_text(source))
    return bool(command and directive_text(source)[command.end():].strip())


def multiple_commands(source: str) -> bool:
    text = directive_text(source)
    markers = list(PAGE_MARKER.finditer(text))
    if len(markers) > 1 and re.search(r'\b(?:va|and)\s+(?:trang|page)\b', text):
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
    if (has_multiple_page_targets(source) and len(categories) > 1
            and not creation_evidence(source)):
        return True
    # Two different Writing operations stay unclear even with one source.
    return False


def deterministic_result(request: IntentRequest) -> IntentResult | None:
    source = request.instruction
    if unsafe_override(source) or multiple_commands(source):
        return result('UNCLEAR')
    if is_page_summary(source) or is_read_only(source) or unsupported_request(source):
        return result('OTHER')
    text = directive_text(source)
    if creation_evidence(source) and CREATE_COMMAND.match(text):
        return result('CREATE_PAGE')
    has_page = bool(PAGE_MARKER.search(text))
    action = writing_action(source)
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
    return None
