import logging

from pydantic import ValidationError

from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import LLMProvider
from app.modules.page_intent.prompts.page_intent_prompt import SYSTEM_PROMPT
from app.modules.page_intent.schemas.page_intent_schema import (
    PageIntentExtraction,
    PageIntentRequest,
    PageIntentResponse,
)
from app.modules.page_intent.services.page_reference_evidence import (
    detect_page_reference,
    explicit_trailing_page_edit,
    is_standalone_writing_request,
    normalize,
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
                result = self._validate_and_ground(raw, request.instruction)
                break
            except RetryablePageIntentError as exc:
                logger.warning(
                    "page_intent_retryable_output kind=%s attempt=%d model=%s",
                    type(exc).__name__,
                    attempt + 1,
                    self.llm_provider.model_name,
                )
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
    def _validate_and_ground(raw: dict, source: str) -> PageIntentExtraction:
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
            evidence = detect_page_reference(source)
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
            evidence = detect_page_reference(source)
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
        evidence = detect_page_reference(source)
        candidate = raw["pageReference"]
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
        instruction = evidence.instruction or raw["instruction"]
        return PageIntentExtraction.model_validate({
            "intent": "MODIFY_PAGE",
            "referenceType": reference_type,
            "pageReference": page_reference,
            "instruction": instruction,
            "needsClarification": needs_clarification,
        })
