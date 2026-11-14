import logging

from pydantic import ValidationError

from app.modules.modification_planner.services.sentence_normalize import normalize_edit_instruction
from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMProvider
from app.modules.intent.prompts.intent_prompt import build_intent_prompt
from app.modules.intent.schemas.intent_schema import IntentExtraction, IntentRequest, IntentResponse, IntentResult
from app.modules.intent.services.intent_rules import (
    PAGE_WORD, creation_evidence, deterministic_result, directive_text, edit_evidence,
    inline_source, is_page_summary, is_read_only, multiple_commands, named_languages, names_page_as_place, result,
    translation_language, unsafe_override, unsupported_request, writing_action,
)
from app.modules.page_intent.services.page_reference_evidence import (
    content_page_reference, detect_with_titles,
)
from app.shared.json_parser import parse_json_object


logger = logging.getLogger(__name__)


class IntentService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    async def process(self, request: IntentRequest) -> IntentResponse:
        # Kế hoạch sửa lỗi người dùng giả lập (S2): "bạn có thể sửa giúp tôi … được
        # không" is read like "sửa …", as the planner rules read it.
        normalized = normalize_edit_instruction(request.instruction)
        if normalized != request.instruction:
            request = request.model_copy(update={"instruction": normalized})
        deterministic = deterministic_result(request)
        if deterministic is not None:
            return IntentResponse(
                result=self._validate_context(deterministic, request),
                provider='deterministic', model='intent-rules-v1',
            )
        system_prompt, user_prompt = build_intent_prompt(request)
        for attempt in range(2):
            generated = await self.llm_provider.generate(
                system_prompt=system_prompt, user_prompt=user_prompt,
                max_new_tokens=200, response_schema=IntentExtraction.model_json_schema(),
            )
            try:
                raw = parse_json_object(generated.text)
            except ValueError as exc:
                logger.warning('intent_invalid_json provider=%s model=%s attempt=%d',
                               self.llm_provider.provider_name, self.llm_provider.model_name, attempt + 1)
                if attempt == 0:
                    continue
                raise InvalidLLMResponseError('AI intent classification returned invalid JSON.') from exc
            try:
                classification = IntentExtraction.model_validate(raw)
            except (ValidationError, ValueError, TypeError) as exc:
                # Unknown fields/IDs and schema violations fail closed. Never
                # log the exception string, which may contain private values.
                logger.warning('intent_invalid_schema provider=%s model=%s error_type=%s',
                               self.llm_provider.provider_name, self.llm_provider.model_name, type(exc).__name__)
                raise InvalidLLMResponseError('AI intent classification returned an invalid result.') from exc
            return IntentResponse(
                result=self._validate_context(classification, request),
                provider=self.llm_provider.provider_name, model=self.llm_provider.model_name,
            )
        raise AssertionError('Intent retry loop exhausted unexpectedly')

    @staticmethod
    def _validate_context(classification: IntentExtraction, request: IntentRequest) -> IntentResult:
        source = request.instruction
        if unsafe_override(source) or multiple_commands(source):
            return result('UNCLEAR')
        if isinstance(classification, IntentResult) and classification.intent == 'PAGE_QUESTION':
            return classification
        # M7 (H1): "tìm trang có nói về X rồi thêm …" starts like a read-only
        # request but edits the Page it finds.
        if classification.intent == 'MODIFY_PAGE' and content_page_reference(source) is not None:
            return result('MODIFY_PAGE')
        selected = bool(request.selectedText)
        reads_selection = selected and writing_action(source, selected=True) is not None
        if (is_read_only(source) and not reads_selection) or is_page_summary(source) or unsupported_request(source):
            return result('OTHER')
        if classification.intent in ('OTHER', 'UNCLEAR'):
            # A model's conservative answer must not be promoted to mutation.
            return result(classification.intent)
        if classification.intent == 'CREATE_PAGE':
            if creation_evidence(source):
                return result('CREATE_PAGE')
            new_page = (PAGE_WORD.search(directive_text(source)) and not request.pageTitles
                        and not edit_evidence(request) and not names_page_as_place(source))
            return result('CREATE_PAGE') if new_page else result('UNCLEAR')
        if classification.intent == 'MODIFY_PAGE':
            if creation_evidence(source) or not (edit_evidence(request) or request.pageTitles):
                return result('UNCLEAR')
            action = writing_action(source, selected=selected)
            has_page = bool(PAGE_WORD.search(directive_text(source)))
            if action and not has_page and (request.selectedText or inline_source(source)):
                return result('UNCLEAR')
            if not has_page and not request.currentPageId:
                return result('UNCLEAR')
            evidence = detect_with_titles(source, has_current_page=bool(request.currentPageId),
                                          titles=tuple(request.pageTitles))
            return result('MODIFY_PAGE', clarify=evidence.reference_type == 'UNRESOLVED'
                          or evidence.reference_type == 'CURRENT_PAGE' and not request.currentPageId)
        rule_action = writing_action(source, soft=True, selected=selected)
        if ((rule_action is not None and rule_action != classification.writingAction)
                or not (request.selectedText or inline_source(source))
                or PAGE_WORD.search(directive_text(source))):
            return result('UNCLEAR')
        action = classification.writingAction
        if action == 'TRANSLATE':
            language = translation_language(source)
            agreed = (classification.language == language if language is not None
                      else classification.language in named_languages(source))
            if not agreed:
                return result('UNCLEAR')
        elif rule_action is None and named_languages(source):
            return result('UNCLEAR')
        return result('WRITING', action, classification.language)
