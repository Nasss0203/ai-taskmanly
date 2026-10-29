import logging

from pydantic import ValidationError

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMProvider
from app.modules.page_intent.prompts.page_intent_prompt import SYSTEM_PROMPT
from app.modules.page_intent.schemas.page_intent_schema import (
    ActivityPageIntent,
    DescriptionPageIntent,
    ScopedTitlePageIntent,
    PageIntentExtraction,
    PageIntentRequest,
    PageIntentResponse,
)
from app.modules.page_intent.services.page_reference_evidence import (
    activity_page_reference,
    description_page_reference,
    detect_page_reference,
    scoped_page_reference,
    explicit_trailing_page_edit,
    is_standalone_writing_request,
    is_read_only_page_request,
    normalize,
    source_backed_edit_instruction,
)
from app.shared.json_parser import parse_json_object


logger = logging.getLogger(__name__)


class RetryablePageIntentError(ValueError):
    """Transient LLM output inconsistency, safe to re-request once."""


class PageIntentTitleMismatch(RetryablePageIntentError):
    """LLM proposed a title different from the explicit user-supplied title."""


class PageIntentService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    async def process(self, request: PageIntentRequest) -> PageIntentResponse:
        # A delimited, explicitly named Page followed by a clear edit clause
        # needs no model inference. This also avoids unstable OTHER/UNCLEAR
        # classifications and exhausted JSON retries for this narrow syntax.
        # M2: "… vào trang tôi sửa hôm qua" names the Page by the user's own
        # edits. Only these rules recognise it; the model never returns it.
        activity = activity_page_reference(request.instruction)
        if activity is not None:
            instruction, reference = activity
            return PageIntentResponse(
                result=ActivityPageIntent.model_validate({
                    "intent": "MODIFY_PAGE",
                    "referenceType": "ACTIVITY",
                    "pageReference": None,
                    "instruction": instruction,
                    "needsClarification": False,
                    "activity": {
                        "relative": reference.relative,
                        "days": reference.days,
                        "titleHint": reference.title_hint,
                    },
                }),
                provider="deterministic",
                model="activity-page-reference-v1",
            )
        # M6: "… vào trang dùng để chuẩn bị phát hành" names a Page by what it
        # is for; NestJS offers the Pages closest to that description. Before
        # M4: "trang theo dõi lỗi của ứng dụng" is a description, not a place.
        described = description_page_reference(request.instruction)
        if described is not None:
            instruction, description = described
            return PageIntentResponse(
                result=DescriptionPageIntent.model_validate({
                    "intent": "MODIFY_PAGE",
                    "referenceType": "DESCRIPTION",
                    "pageReference": None,
                    "instruction": instruction,
                    "needsClarification": False,
                    "description": description,
                }),
                provider="deterministic",
                model="description-page-reference-v1",
            )
        # M4: "… vào trang Tasks trong trang Dự án A" names a Page and where
        # it is; NestJS narrows the Pages titled "Tasks" to that place.
        scoped = scoped_page_reference(request.instruction)
        if scoped is not None:
            instruction, title, scope = scoped
            return PageIntentResponse(
                result=ScopedTitlePageIntent.model_validate({
                    "intent": "MODIFY_PAGE",
                    "referenceType": "TITLE",
                    "pageReference": title,
                    "instruction": instruction,
                    "needsClarification": False,
                    "scope": {
                        "parentTitle": scope.parent_title,
                        "teamspaceName": scope.teamspace_name,
                    },
                }),
                provider="deterministic",
                model="scoped-page-reference-v1",
            )
        explicit = explicit_trailing_page_edit(request.instruction)
        if explicit is not None:
            return PageIntentResponse(
                result=PageIntentExtraction.model_validate({
                    "intent": "MODIFY_PAGE",
                    "referenceType": "TITLE",
                    "pageReference": explicit.title,
                    "instruction": explicit.instruction,
                    "needsClarification": False,
                }),
                provider="deterministic",
                model="explicit-page-reference-v1",
            )
        # Retry transient JSON/semantic inconsistencies exactly once,
        # always validating against the original user text. Never retry
        # unknown fields (especially hallucinated pageId), missing fields,
        # or wrong primitive types: these are contract boundary violations.
        for attempt in range(2):
            generated = await self.llm_provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=request.instruction,
                max_new_tokens=300,
                response_schema=PageIntentExtraction.model_json_schema(),
            )
            try:
                try:
                    raw = parse_json_object(generated.text)
                except ValueError as exc:
                    raise RetryablePageIntentError("Model returned invalid JSON.") from exc
                result = self._validate_and_ground(
                    raw, request.instruction, has_current_page=bool(request.currentPageId),
                )
                break
            except RetryablePageIntentError as exc:
                logger.warning(
                    "page_intent_retryable_output kind=%s attempt=%d model=%s",
                    type(exc).__name__,
                    attempt + 1,
                    self.llm_provider.model_name,
                )
                if attempt == 1 and isinstance(exc, PageIntentTitleMismatch):
                    # Disagreement on where a bare name ends is not an error:
                    # use neither title and let NestJS match real Page names.
                    result = self._unresolved_edit(
                        request.instruction, has_current_page=bool(request.currentPageId),
                    )
                    break
                if attempt == 1:
                    raise InvalidLLMResponseError(
                        "AI page intent extraction returned an invalid result."
                    ) from exc
            except (ValidationError, ValueError, TypeError) as exc:
                logger.warning(
                    "page_intent_invalid_output kind=%s model=%s",
                    type(exc).__name__,
                    self.llm_provider.model_name,
                )
                raise InvalidLLMResponseError(
                    "AI page intent extraction returned an invalid result."
                ) from exc

        return PageIntentResponse(
            result=result,
            provider=self.llm_provider.provider_name,
            model=self.llm_provider.model_name,
        )

    @staticmethod
    def _unresolved_edit(source: str, *, has_current_page: bool) -> PageIntentExtraction:
        # A title mismatch is only raised after the source-backed edit check.
        evidence = detect_page_reference(source, has_current_page=has_current_page)
        return PageIntentExtraction.model_validate({
            "intent": "MODIFY_PAGE",
            "referenceType": "UNRESOLVED",
            "pageReference": None,
            "instruction": source_backed_edit_instruction(source, evidence),
            "needsClarification": True,
        })

    @staticmethod
    def _validate_and_ground(
        raw: dict, source: str, *, has_current_page: bool = False,
    ) -> PageIntentExtraction:
        # Even a model-generated pageId or unknown field invalidates the whole
        # response. Do not silently strip untrusted fields.
        required = {
            "intent", "referenceType", "pageReference",
            "instruction", "needsClarification",
        }
        if set(raw) != required:
            raise ValueError("LLM returned unknown or missing fields.")
        if (
            raw["intent"] not in ("MODIFY_PAGE", "OTHER", "UNCLEAR")
            or raw["referenceType"] not in ("TITLE", "CURRENT_PAGE", "UNRESOLVED")
            or type(raw["needsClarification"]) is not bool
            or not (raw["pageReference"] is None or type(raw["pageReference"]) is str)
            or not (raw["instruction"] is None or type(raw["instruction"]) is str)
        ):
            raise ValueError("LLM returned fields with invalid types.")

        if raw["intent"] == "OTHER":
            # The 4B model sometimes puts a redundant instruction into OTHER.
            # No editing instruction should escape the non-modification branch.
            if raw["referenceType"] != "UNRESOLVED" or raw["pageReference"] is not None:
                raise RetryablePageIntentError("OTHER must not refer to an existing Page.")
            evidence = detect_page_reference(source, has_current_page=has_current_page)
            if evidence.reference_type in ("TITLE", "CURRENT_PAGE") and evidence.instruction:
                return PageIntentExtraction.model_validate({
                    "intent": "MODIFY_PAGE",
                    "referenceType": evidence.reference_type,
                    "pageReference": evidence.title,
                    "instruction": evidence.instruction,
                    "needsClarification": False,
                })
            return PageIntentExtraction.model_validate({
                **raw, "instruction": None, "needsClarification": False,
            })

        if raw["intent"] == "UNCLEAR":
            if raw["referenceType"] != "UNRESOLVED" or raw["pageReference"] is not None:
                raise RetryablePageIntentError("UNCLEAR must not refer to an existing Page.")
            evidence = detect_page_reference(source, has_current_page=has_current_page)
            if evidence.reference_type in ("TITLE", "CURRENT_PAGE") and evidence.instruction:
                return PageIntentExtraction.model_validate({
                    "intent": "MODIFY_PAGE",
                    "referenceType": evidence.reference_type,
                    "pageReference": evidence.title,
                    "instruction": evidence.instruction,
                    "needsClarification": False,
                })
            # A direct informational question is not a Page editing request.
            is_page_definition_question = normalize(source).strip(" !?.,").strip() in {
                "page là gì", "trang là gì", "what is a page",
            }
            return PageIntentExtraction.model_validate({
                **raw,
                "intent": "OTHER" if is_page_definition_question else "UNCLEAR",
                "instruction": None,
                "needsClarification": not is_page_definition_question,
            })

        if raw["instruction"] is None or not raw["instruction"].strip():
            raise ValueError("MODIFY_PAGE must contain an instruction.")

        if is_standalone_writing_request(source):
            return PageIntentExtraction.model_validate({
                "intent": "OTHER",
                "referenceType": "UNRESOLVED",
                "pageReference": None,
                "instruction": None,
                "needsClarification": False,
            })

        # Only an actual modification may carry an instruction. A target
        # derived from syntactic evidence overrides an LLM's unsafe guess.
        evidence = detect_page_reference(source, has_current_page=has_current_page)
        instruction = source_backed_edit_instruction(source, evidence)
        if instruction is None:
            read_only = is_read_only_page_request(source)
            return PageIntentExtraction.model_validate({
                "intent": "OTHER" if read_only else "UNCLEAR",
                "referenceType": "UNRESOLVED",
                "pageReference": None,
                "instruction": None,
                "needsClarification": not read_only,
            })
        candidate = raw["pageReference"]
        if raw["referenceType"] == "TITLE" and not (candidate or "").strip():
            # A contract violation stays an error; only a name disagreement is unresolved.
            raise RetryablePageIntentError("TITLE requires a pageReference.")
        if evidence.reference_type == "TITLE" and raw["referenceType"] == "TITLE":
            grounded_title = normalize(evidence.title or "").strip()
            candidate_title = normalize(candidate or "").strip()
            if candidate_title != grounded_title:
                # Small models sometimes truncate a multi-word explicit title,
                # especially its random/version suffix. Safely restore only
                # when the candidate is a whole-word prefix of the title
                # taken from the ORIGINAL input. Never accept invented text.
                whole_word_prefix = (
                    len(candidate_title.split()) >= 2
                    and grounded_title.startswith(candidate_title + " ")
                )
                if whole_word_prefix:
                    logger.info("page_intent_title_suffix_restored")
                else:
                    raise PageIntentTitleMismatch(
                        "LLM page title disagrees with explicit source reference."
                    )
        if evidence.reference_type == "UNRESOLVED":
            reference_type, page_reference, needs_clarification = (
                "UNRESOLVED", None, True,
            )
        elif evidence.reference_type == "CURRENT_PAGE":
            reference_type, page_reference, needs_clarification = (
                "CURRENT_PAGE", None, False,
            )
        else:
            reference_type, page_reference, needs_clarification = (
                "TITLE", evidence.title, False,
            )
        return PageIntentExtraction.model_validate({
            "intent": "MODIFY_PAGE",
            "referenceType": reference_type,
            "pageReference": page_reference,
            "instruction": instruction,
            "needsClarification": needs_clarification,
        })
