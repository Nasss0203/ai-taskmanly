from __future__ import annotations
import logging
import re
import unicodedata
from time import perf_counter
from typing import Any, NoReturn
from pydantic import TypeAdapter, ValidationError
from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import (
    LLMGenerationResult,
    LLMProvider,
    LLMTokenUsage,
    answered_by,
)
from app.modules.modification_planner.prompts.modification_planner_prompt import (
    build_create_database_rows_generation_prompt,
    build_insert_blocks_generation_prompt,
    build_mixed_operations_generation_prompt,
    build_modification_planner_route_prompt,
    build_need_more_context_generation_prompt,
)
from app.modules.modification_planner.schemas.modification_planner_schema import (
    AiModificationPlan,
    AiPageContext,
    ChecklistInsertBlocksOperationBatch,
    ChecklistMixedModificationOperationBatch,
    ChecklistWithHeadingInsertBlocksOperationBatch,
    ChecklistWithHeadingMixedModificationOperationBatch,
    CreateDatabaseRowsOperationBatch,
    InsertBlocksOperationBatch,
    MixedModificationOperationBatch,
    ModificationNeedMoreContextDetails,
    ModificationPlannerRequest,
    ModificationPlannerResponse,
    ModificationPlannerRoute,
    ModificationPlannerUsage,
)
from app.modules.modification_planner.validators.modification_planner_semantic_validator import (
    ModificationPlannerSemanticValidationError,
    validate_modification_plan_semantics,
)
from app.shared.json_parser import parse_json_object
from app.modules.modification_planner.services.block_delete import plan_block_delete
from app.modules.modification_planner.services.database_rows import (
    DATABASE_ROWS_MODEL,
    ROWS_AND_BLOCKS_MODEL,
    plan_database_rows,
    plan_rows_and_blocks,
)
from app.modules.modification_planner.services.missing_target import MISSING_TARGET_MODEL, plan_missing_target
from app.modules.modification_planner.services.context_window import window_context
from app.modules.modification_planner.services.explicit_plan import EXPLICIT_CONTENT_MODEL, plan_explicit_content
from app.modules.modification_planner.services.explicit_content import mentions_position, parse_explicit_blocks
from app.modules.modification_planner.services.sentence_text import QUOTES, command_text
from app.modules.modification_planner.services.block_text import plan_block_text
from app.modules.modification_planner.services.sentence_normalize import normalize_instruction
from app.modules.modification_planner.services.todo_status import (
    TODO_STATUS_MODEL,
    TODO_STATUS_PROVIDER,
    plan_todo_status,
)
from app.shared.list_markers import has_list_marker, strip_list_marker
from app.modules.modification_planner.services.reference_grounding import keep_grounded_blocks
from app.modules.modification_planner.services.reference_checklist import (
    REFERENCE_CHECKLIST_MODEL,
    REFERENCE_CHECKLIST_PROVIDER,
    plan_reference_checklist,
)
logger = logging.getLogger(__name__)
PLAN_ADAPTER = TypeAdapter(AiModificationPlan)
ROUTE_ADAPTER = TypeAdapter(
    ModificationPlannerRoute,
)
INSERT_BLOCKS_BATCH_ADAPTER = TypeAdapter(
    InsertBlocksOperationBatch,
)

CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER = TypeAdapter(
    ChecklistInsertBlocksOperationBatch,
)
CREATE_DATABASE_ROWS_BATCH_ADAPTER = TypeAdapter(
    CreateDatabaseRowsOperationBatch,
)
MIXED_OPERATIONS_BATCH_ADAPTER = TypeAdapter(
    MixedModificationOperationBatch,
)

CHECKLIST_MIXED_OPERATIONS_BATCH_ADAPTER = TypeAdapter(
    ChecklistMixedModificationOperationBatch,
)
CHECKLIST_WITH_HEADING_INSERT_BLOCKS_BATCH_ADAPTER = TypeAdapter(
    ChecklistWithHeadingInsertBlocksOperationBatch,
)
CHECKLIST_WITH_HEADING_MIXED_OPERATIONS_BATCH_ADAPTER = TypeAdapter(
    ChecklistWithHeadingMixedModificationOperationBatch,
)
NEED_MORE_CONTEXT_DETAILS_ADAPTER = TypeAdapter(
    ModificationNeedMoreContextDetails,
)
ROUTER_MAX_NEW_TOKENS = 256
BLOCK_TEXT_MODEL = "block-text-v1"
BLOCK_DELETE_MODEL = "block-delete-v1"
GENERATION_MAX_NEW_TOKENS = 1200
# Kế hoạch trang dài (E2): prompt budget for the Page context.
DEFAULT_NUM_CTX = 6144
PROMPT_FIXED_TOKENS = 2150  # ~1.850 measured + margin
MIN_CONTEXT_BUDGET_TOKENS = 1200

HEADING_INTENT_TERMS = ("heading", "header", "tiêu đề", "đề mục")

CHECKLIST_INTENT_TERMS = (
    "checklist",
    "check list",
    "task list",
    "todo",
    "to-do",
)

# "checklist gồm a, b và c" -> items a, b, c.
CHECKLIST_ITEMS_LEAD = re.compile(r"^\s*(?:bao gồm|gồm|là|với)?\s*:?\s*")
# "checklist chuẩn bị họp gồm a, b" -> name "chuẩn bị họp", items a, b.
CHECKLIST_ITEMS_MARKER = re.compile(r"\b(?:bao gồm|gồm)\b\s*:?\s*|:\s*")
CHECKLIST_ITEM_SEPARATOR = re.compile(r"\s*(?:[,;]|\bvà\b)\s*")
# gp16: the topic of "thêm checklist ôn tập môn Anh (vào cuối trang)", in the user's words.
CHECKLIST_TERM = re.compile(r"check\s?list|task list|to-?do", re.IGNORECASE)
TOPIC_POSITION = re.compile(
    r"\s+(?:(?:vào|ở|tại|dưới|sau|trước|trong)\s+(?:cuối|đầu|phần|mục|heading|tiêu đề|trang|block|dòng|đoạn|toggle)\b"
    r"|(?:at|to|in|into|under|after|before|below|above|on)\s+the\s)",
    re.IGNORECASE,
)
# A topic still holding a position word was not cut cleanly: keep the model's items.
TOPIC_UNSURE = re.compile(
    r"\b(?:under|at|to|in|into|on|after|before|below|above|vào|ở|tại|dưới|sau|trước|trong)\b", re.IGNORECASE,
)
TOPIC_ITEM_WORD = re.compile(r"^\s*(?:items?|mục)\b", re.IGNORECASE)


class ModificationPlannerService:
    def __init__(
        self,
        llm_provider: LLMProvider,
    ) -> None:
        self.llm_provider = llm_provider
    async def process(
        self,
        request: ModificationPlannerRequest,
    ) -> ModificationPlannerResponse:
        # Kế hoạch sửa lỗi người dùng giả lập (S2–S5): everyday wording ("bạn có
        # thể sửa giúp tôi A thành B được không") in the forms the rules read.
        normalized = normalize_instruction(request.instruction)
        if normalized != request.instruction:
            request = request.model_copy(update={"instruction": normalized})
        # Ticks, text edits and deletes of existing blocks are matched by rules,
        # never by the model (kế hoạch tích to-do, sửa chữ block, xoá block).
        for plan_by_rules, model in (
            (plan_todo_status, TODO_STATUS_MODEL),
            (plan_block_text, BLOCK_TEXT_MODEL),
            (plan_block_delete, BLOCK_DELETE_MODEL),
            # A named section or table the Page lacks is asked back, never guessed.
            (plan_missing_target, MISSING_TARGET_MODEL),
            # Kế hoạch sửa lỗi tạo trang và bảng (P6): rows of a named table.
            (plan_database_rows, DATABASE_ROWS_MODEL),
            (plan_rows_and_blocks, ROWS_AND_BLOCKS_MODEL),
        ):
            rule_plan = plan_by_rules(request.instruction, request.context)
            if rule_plan is not None:
                validate_modification_plan_semantics(rule_plan, request.context)
                logger.info("modification_planner_rules model=%s status=%s", model, rule_plan.status)
                return ModificationPlannerResponse(
                    result=rule_plan,
                    provider=TODO_STATUS_PROVIDER,
                    model=model,
                )
        # M8: a checklist of a named source Page's items under the heading the
        # user named, or of all its items, is picked by rule.
        checklist = plan_reference_checklist(
            request.instruction, request.context.page.id, request.references,
        )
        if checklist is not None:
            validate_modification_plan_semantics(checklist, request.context)
            logger.info("modification_planner_rules model=%s status=%s", REFERENCE_CHECKLIST_MODEL, checklist.status)
            return ModificationPlannerResponse(
                result=checklist,
                provider=REFERENCE_CHECKLIST_PROVIDER,
                model=REFERENCE_CHECKLIST_MODEL,
            )
        # Kế hoạch bỏ qua model (F1): content and place are fully spelled out.
        explicit = plan_explicit_content(request.instruction, request.context, request.references)
        if explicit is not None:
            validate_modification_plan_semantics(explicit, request.context)
            logger.info("modification_planner_rules model=%s status=%s", EXPLICIT_CONTENT_MODEL, explicit.status)
            return ModificationPlannerResponse(
                result=explicit,
                provider=TODO_STATUS_PROVIDER,
                model=EXPLICIT_CONTENT_MODEL,
            )
        context_payload = self._serialize_context(
            request.context,
            request.instruction,
        )
        started_at = perf_counter()
        logger.info(
            "modification_planner_started provider=%s model=%s",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
        )
        route_generation = await self._generate_route(
            request=request,
            context_payload=context_payload,
        )
        try:
            route = self._parse_route(
                generation=route_generation,
            )
        except (
            ValueError,
            ValidationError,
            TypeError,
        ) as exc:
            self._raise_invalid_response(
                exc=exc,
            )
        stage_two_generation = (
            await self._generate_stage_two(
                request=request,
                context_payload=context_payload,
                route=route,
            )
        )
        try:
            plan = self._build_plan_from_stage_two(
                request=request,
                route=route,
                generation=stage_two_generation,
            )
            plan = self._reanchor_non_toggle_parents(plan, request.context)
            validate_modification_plan_semantics(
                plan,
                request.context,
            )
            plan = self._checklist_items_as_todos(plan, request.instruction)
            plan = self._drop_checklist_name_todo(plan, request.instruction)
            plan = self._single_topic_checklist(plan, request)
            plan = self._todo_list_toggles(plan, request.context)
            plan = self._lock_explicit_content(plan, request)
            plan = self._default_position(plan, request)
            plan = self._strip_todo_list_markers(plan)
            plan = self._keep_grounded_items(plan, request)
        except (
            ModificationPlannerSemanticValidationError,
            ValueError,
            ValidationError,
            TypeError,
        ) as exc:
            self._raise_invalid_response(
                exc=exc,
            )
        total_usage = self._combine_usage(
            route_generation.usage,
            stage_two_generation.usage,
        )
        logger.info(
            "modification_planner_succeeded "
            "provider=%s model=%s latency_ms=%.2f",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
            (perf_counter() - started_at) * 1000,
        )
        provider_name, model_name = answered_by(stage_two_generation, self.llm_provider)
        if total_usage is None:
            return ModificationPlannerResponse(
                result=plan,
                provider=provider_name,
                model=model_name,
            )
        return ModificationPlannerResponse(
            result=plan,
            provider=provider_name,
            model=model_name,
            usage=ModificationPlannerUsage(
                prompt_tokens=total_usage.prompt_tokens,
                completion_tokens=(
                    total_usage.completion_tokens
                ),
                total_tokens=total_usage.total_tokens,
            ),
        )
    @staticmethod
    def _references(request: ModificationPlannerRequest) -> list[dict[str, Any]] | None:
        """M8: the read-only passages NestJS found in the source the user named."""
        if not request.references:
            return None
        return [reference.model_dump(mode="json") for reference in request.references]

    async def _generate_route(
        self,
        request: ModificationPlannerRequest,
        context_payload: dict[str, Any],
    ) -> LLMGenerationResult:
        system_prompt, user_prompt = (
            build_modification_planner_route_prompt(
                instruction=request.instruction,
                context=context_payload,
                references=self._references(request),
            )
        )
        return await self._generate(
            stage="route",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_new_tokens=ROUTER_MAX_NEW_TOKENS,
            response_schema=ROUTE_ADAPTER.json_schema(),
        )
    def _parse_route(
        self,
        generation: LLMGenerationResult,
    ) -> ModificationPlannerRoute:
        raw_route = parse_json_object(
            generation.text,
        )
        return ROUTE_ADAPTER.validate_python(
            raw_route,
        )
    async def _generate_stage_two(
        self,
        request: ModificationPlannerRequest,
        context_payload: dict[str, Any],
        route: ModificationPlannerRoute,
    ) -> LLMGenerationResult:
        if route.status == "NEED_MORE_CONTEXT":
            system_prompt, user_prompt = (
                build_need_more_context_generation_prompt(
                    instruction=request.instruction,
                    context=context_payload,
                    references=self._references(request),
                )
            )
            response_schema = (
                NEED_MORE_CONTEXT_DETAILS_ADAPTER.json_schema()
            )
            return await self._generate(
                stage="need_more_context",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=GENERATION_MAX_NEW_TOKENS,
                response_schema=response_schema,
            )
        operation_types = frozenset(
            route.operationTypes,
        )
        if operation_types == {
            "INSERT_BLOCKS",
        }:
            system_prompt, user_prompt = (
                build_insert_blocks_generation_prompt(
                    instruction=request.instruction,
                    context=context_payload,
                    references=self._references(request),
                )
            )
            response_schema = self._insert_blocks_adapter(
                request.instruction,
            ).json_schema()
            return await self._generate(
                stage="insert_blocks",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=GENERATION_MAX_NEW_TOKENS,
                response_schema=response_schema,
            )
        if operation_types == {
            "CREATE_DATABASE_ROWS",
        }:
            system_prompt, user_prompt = (
                build_create_database_rows_generation_prompt(
                    instruction=request.instruction,
                    context=context_payload,
                    references=self._references(request),
                )
            )
            response_schema = (
                CREATE_DATABASE_ROWS_BATCH_ADAPTER.json_schema()
            )
            return await self._generate(
                stage="create_database_rows",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=GENERATION_MAX_NEW_TOKENS,
                response_schema=response_schema,
            )
        if operation_types == {
            "CREATE_DATABASE_ROWS",
            "INSERT_BLOCKS",
        }:
            system_prompt, user_prompt = (
                build_mixed_operations_generation_prompt(
                    instruction=request.instruction,
                    context=context_payload,
                    references=self._references(request),
                )
            )
            response_schema = self._mixed_operations_adapter(
                request.instruction,
            ).json_schema()
            return await self._generate(
                stage="mixed_operations",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=GENERATION_MAX_NEW_TOKENS,
                response_schema=response_schema,
            )
        raise InvalidLLMResponseError(
            "Modification planner route is invalid."
        )
    def _build_plan_from_stage_two(
        self,
        request: ModificationPlannerRequest,
        route: ModificationPlannerRoute,
        generation: LLMGenerationResult,
    ) -> AiModificationPlan:
        raw_result = parse_json_object(
            generation.text,
        )
        if route.status == "NEED_MORE_CONTEXT":
            details = (
                NEED_MORE_CONTEXT_DETAILS_ADAPTER.validate_python(
                    raw_result,
                )
            )
            plan_payload = {
                "schemaVersion": 1,
                "type": "AI_MODIFICATION_PLAN",
                "pageId": request.context.page.id,
                "status": "NEED_MORE_CONTEXT",
                "summary": details.summary,
                "operations": [],
                "contextRequests": [
                    context_request.model_dump(
                        mode="json",
                        exclude_unset=True,
                    )
                    for context_request
                    in details.contextRequests
                ],
            }
            return PLAN_ADAPTER.validate_python(
                plan_payload,
            )
        operation_types = frozenset(
            route.operationTypes,
        )
        if operation_types == {
            "INSERT_BLOCKS",
        }:
            batch = self._insert_blocks_adapter(
                request.instruction,
            ).validate_python(raw_result)

            operations = [
                operation.model_dump(
                    mode="json",
                    exclude_unset=True,
                )
                for operation in batch.operations
            ]
        elif operation_types == {
            "CREATE_DATABASE_ROWS",
        }:
            batch = (
                CREATE_DATABASE_ROWS_BATCH_ADAPTER.validate_python(
                    raw_result,
                )
            )
            operations = [
                operation.model_dump(
                    mode="json",
                    exclude_unset=True,
                )
                for operation in batch.operations
            ]
        elif operation_types == {
            "CREATE_DATABASE_ROWS",
            "INSERT_BLOCKS",
        }:
            batch = self._mixed_operations_adapter(
                request.instruction,
            ).validate_python(raw_result)

            database_operations = [
                operation.model_dump(
                    mode="json",
                    exclude_unset=True,
                )
                for operation
                in batch.createDatabaseRowsOperations
            ]
            insert_operations = [
                operation.model_dump(
                    mode="json",
                    exclude_unset=True,
                )
                for operation
                in batch.insertBlocksOperations
            ]
            operations = []
            for operation_type in route.operationTypes:
                if operation_type == "CREATE_DATABASE_ROWS":
                    operations.extend(
                        database_operations,
                    )
                elif operation_type == "INSERT_BLOCKS":
                    operations.extend(
                        insert_operations,
                    )
        else:
            raise ValueError(
                "Unsupported modification planner route."
            )
        plan_payload = {
            "schemaVersion": 1,
            "type": "AI_MODIFICATION_PLAN",
            "pageId": request.context.page.id,
            "status": "PLAN_READY",
            "summary": request.instruction.strip(),
            "operations": operations,
        }
        return PLAN_ADAPTER.validate_python(
            plan_payload,
        )
    @staticmethod
    def _keep_grounded_items(plan: Any, request: ModificationPlannerRequest) -> Any:
        """M8 (I5): with references, an item from neither a passage nor the
        request is dropped; nothing left means the source did not hold it."""
        if not request.references or plan.status != "PLAN_READY":
            return plan
        data = plan.model_dump(mode="json", exclude_unset=True)
        operations, dropped = keep_grounded_blocks(
            data.get("operations") or [],
            [reference.text for reference in request.references],
            request.instruction,
        )
        if not dropped:
            return plan
        logger.info("modification_planner_ungrounded_items dropped=%d", dropped)
        if operations:
            return PLAN_ADAPTER.validate_python({**data, "operations": operations})
        return PLAN_ADAPTER.validate_python({
            "schemaVersion": 1,
            "type": "AI_MODIFICATION_PLAN",
            "pageId": data["pageId"],
            "status": "NEED_MORE_CONTEXT",
            "summary": "Nguồn không có nội dung khớp yêu cầu.",
            "operations": [],
            "contextRequests": [{
                "reason": "MISSING_RESOURCE_CONTEXT",
                "description": "Các đoạn trích từ trang nguồn không có mục nào khớp yêu cầu.",
            }],
        })

    @staticmethod
    def _reanchor_non_toggle_parents(plan: Any, context: Any) -> Any:
        # Only a TOGGLE holds children. Models name a TEXT/HEADER as parent to
        # mean "under this line": insert right after it, at its own level.
        blocks = {block.id: block for block in context.blocks}
        data = plan.model_dump(mode="json", exclude_unset=True)
        changed = False
        for operation in data.get("operations") or []:
            parent = blocks.get(operation.get("parentBlockId") or "")
            if operation.get("type") != "INSERT_BLOCKS" or parent is None or parent.type == "TOGGLE":
                continue
            operation["parentBlockId"] = parent.parentBlockId
            operation["afterBlockId"] = parent.id
            changed = True
        return type(plan).model_validate(data) if changed else plan

    @staticmethod
    def _checklist_items_as_todos(plan: Any, instruction: str) -> Any:
        # With a heading allowed, models also render listed checklist items as HEADER.
        items = ModificationPlannerService._listed_checklist_items(instruction)
        if not items:
            return plan
        data = plan.model_dump(mode="json", exclude_unset=True)
        changed = False
        for operation in data.get("operations") or []:
            if not operation.get("blocks"):
                continue
            blocks = []
            for block in operation["blocks"]:
                text = (block.get("content") or {}).get("text")
                lines = [line for line in text.splitlines() if line.strip()] if isinstance(text, str) else []
                # gp06: several listed items packed in one block ("• a\n• b") -> one TODO each.
                if (
                    block.get("type") in ("HEADER", "TODO")
                    and (len(lines) > 1 or block.get("type") == "HEADER")
                    and lines
                    and all(ModificationPlannerService._checklist_item_key(line) in items for line in lines)
                ):
                    blocks.extend(
                        {"type": "TODO", "content": {"text": strip_list_marker(line), "checked": False}}
                        for line in lines
                    )
                    changed = True
                else:
                    blocks.append(block)
            operation["blocks"] = blocks
        return type(plan).model_validate(data) if changed else plan

    @staticmethod
    def _lock_explicit_content(plan: Any, request: ModificationPlannerRequest) -> Any:
        # gp31/gp32: the model obeyed words inside the content. Blocks the sentence
        # spells out are taken by rule; the model only chose where they go.
        if request.references or plan.status != "PLAN_READY":
            return plan
        blocks = parse_explicit_blocks(request.instruction)
        data = plan.model_dump(mode="json", exclude_unset=True)
        operations = data.get("operations") or []
        if blocks is None or not operations or any(op.get("type") != "INSERT_BLOCKS" for op in operations):
            return plan
        current = [(block.get("type"), (block.get("content") or {}).get("text"))
                   for op in operations for block in op.get("blocks") or []]
        if len(operations) == 1 and current == blocks:
            return plan
        levels = [block["styleConfig"] for op in operations for block in op.get("blocks") or []
                  if block.get("type") == "HEADER" and block.get("styleConfig")]
        locked = []
        for kind, text in blocks:
            if kind == "TODO":
                locked.append({"type": "TODO", "content": {"text": text, "checked": False}})
            elif kind == "HEADER":
                locked.append({"type": "HEADER", "content": {"text": text},
                               **({"styleConfig": levels.pop(0)} if levels else {})})
            else:
                locked.append({"type": kind, "content": {"text": text}})
        first = operations[0]
        data["operations"] = [{"type": "INSERT_BLOCKS", "parentBlockId": first.get("parentBlockId"),
                               "afterBlockId": first.get("afterBlockId"), "blocks": locked}]
        logger.info("modification_planner_content_locked blocks=%d model_blocks=%d", len(locked), len(current))
        locked_plan = type(plan).model_validate(data)
        validate_modification_plan_semantics(locked_plan, request.context)
        return locked_plan

    @staticmethod
    def _default_position(plan: Any, request: ModificationPlannerRequest) -> Any:
        # Kế hoạch vị trí mặc định (B, DB1 = A): a sentence naming no place goes
        # at the end of the Page, after its last root block. Any place word keeps
        # the model's choice; references (M8) keep their own placement.
        if request.references or plan.status != "PLAN_READY":
            return plan
        if mentions_position(request.instruction, request.context.page.title):
            return plan
        data = plan.model_dump(mode="json", exclude_unset=True)
        operations = data.get("operations") or []
        if len(operations) != 1 or operations[0].get("type") != "INSERT_BLOCKS":
            return plan
        roots = [block for block in request.context.blocks if block.parentBlockId is None]
        last = max(roots, key=lambda block: block.orderIndex).id if roots else None
        operation = operations[0]
        if operation.get("parentBlockId") is None and operation.get("afterBlockId") in (None, last):
            return plan
        logger.info("modification_planner_default_position moved=1")
        operation["parentBlockId"] = None
        operation["afterBlockId"] = last
        moved = type(plan).model_validate(data)
        validate_modification_plan_semantics(moved, request.context)
        return moved

    def _single_topic_checklist(self, plan: Any, request: ModificationPlannerRequest) -> Any:
        # gp16: a checklist given only a topic is one TODO (prompt rule); models still
        # invent steps. Items from a source Page (M8) and heading requests are left alone.
        if request.references or self._requests_heading(request.instruction):
            return plan
        topic = self._checklist_topic(request.instruction)
        if topic is None:
            return plan
        data = plan.model_dump(mode="json", exclude_unset=True)
        holders = [op for op in data.get("operations") or [] if any(
            block.get("type") == "TODO" for block in op.get("blocks") or [])]
        if len(holders) != 1 or len(holders[0]["blocks"]) < 2 or any(
                block.get("type") != "TODO" for block in holders[0]["blocks"]):
            return plan
        holders[0]["blocks"] = [{"type": "TODO", "content": {"text": topic, "checked": False}}]
        return type(plan).model_validate(data)

    @staticmethod
    def _checklist_topic(instruction: str) -> str | None:
        """The one topic of a checklist sentence without listed items, else None."""
        text = unicodedata.normalize("NFC", command_text(instruction))
        # The first term: "to-do X ngay sau to-do Y" is about X, never Y.
        term = CHECKLIST_TERM.search(text)
        if term is None:
            return None
        tail = TOPIC_ITEM_WORD.sub("", text[term.end():], count=1)
        if CHECKLIST_ITEMS_MARKER.search(tail.casefold()):
            return None
        position = TOPIC_POSITION.search(tail)
        if position:
            tail = tail[:position.start()]
        topic = CHECKLIST_ITEMS_LEAD.sub("", tail, count=1).strip(" " + QUOTES + ".!,")
        if not topic or len(CHECKLIST_ITEM_SEPARATOR.split(topic)) > 1 or TOPIC_UNSURE.search(topic):
            return None
        return topic[0].upper() + topic[1:]

    @staticmethod
    def _todo_list_toggles(plan: Any, context: Any) -> Any:
        # gp22: an inserted TOGGLE never has children here; placed in a to-do list
        # ("add Toothbrush to the Packing list") it is one more TODO.
        types = {block.id: block.type for block in context.blocks}
        data = plan.model_dump(mode="json", exclude_unset=True)
        changed = False
        for operation in data.get("operations") or []:
            previous = types.get(operation.get("afterBlockId") or "")
            for index, block in enumerate(operation.get("blocks") or []):
                text = (block.get("content") or {}).get("text")
                if block.get("type") == "TOGGLE" and previous == "TODO" and isinstance(text, str):
                    operation["blocks"][index] = {
                        "type": "TODO", "content": {"text": strip_list_marker(text), "checked": False},
                    }
                    changed = True
                previous = operation["blocks"][index].get("type")
        return type(plan).model_validate(data) if changed else plan

    @staticmethod
    def _drop_checklist_name_todo(plan: Any, instruction: str) -> Any:
        # gp01: in "checklist chuẩn bị họp gồm a, b" models also add the name as a TODO.
        name = ModificationPlannerService._checklist_name(instruction)
        items = ModificationPlannerService._listed_checklist_items(instruction)
        if not name or not items or name in items:
            return plan
        data = plan.model_dump(mode="json", exclude_unset=True)
        changed = False
        for operation in data.get("operations") or []:
            blocks = operation.get("blocks") or []
            kept = [
                block for block in blocks
                if not (
                    block.get("type") == "TODO"
                    and isinstance((block.get("content") or {}).get("text"), str)
                    and ModificationPlannerService._checklist_item_key(block["content"]["text"]) == name
                )
            ]
            if kept and len(kept) < len(blocks):
                operation["blocks"] = kept
                changed = True
        return type(plan).model_validate(data) if changed else plan

    @staticmethod
    def _split_checklist(instruction: str) -> tuple[str, str] | None:
        """Text after the last checklist term, as (name, listed items)."""
        normalized_instruction = unicodedata.normalize("NFC", instruction).casefold()
        positions = [
            normalized_instruction.rfind(term) + len(term)
            for term in CHECKLIST_INTENT_TERMS
            if term in normalized_instruction
        ]
        if not positions:
            return None
        tail = normalized_instruction[max(positions):]
        marker = CHECKLIST_ITEMS_MARKER.search(tail)
        if marker is None:
            return "", CHECKLIST_ITEMS_LEAD.sub("", tail, count=1)
        return tail[:marker.start()], tail[marker.end():]

    @staticmethod
    def _checklist_name(instruction: str) -> str:
        split = ModificationPlannerService._split_checklist(instruction)
        return ModificationPlannerService._checklist_item_key(split[0]) if split else ""

    @staticmethod
    def _listed_checklist_items(instruction: str) -> set[str]:
        split = ModificationPlannerService._split_checklist(instruction)
        if split is None:
            return set()
        return {
            key
            for item in CHECKLIST_ITEM_SEPARATOR.split(split[1])
            if (key := ModificationPlannerService._checklist_item_key(item))
        }

    @staticmethod
    def _checklist_item_key(text: str) -> str:
        key = strip_list_marker(unicodedata.normalize("NFC", text)).strip().rstrip(".!").strip()
        return key.casefold()

    @staticmethod
    def _strip_todo_list_markers(plan: Any) -> Any:
        # A TODO is one list item; models still prefix "1.", "2." to its text.
        data = plan.model_dump(mode="json", exclude_unset=True)
        changed = False
        for operation in data.get("operations") or []:
            for block in operation.get("blocks") or []:
                content = block.get("content")
                if (
                    block.get("type") == "TODO"
                    and isinstance(content, dict)
                    and isinstance(content.get("text"), str)
                    and has_list_marker(content["text"])
                ):
                    content["text"] = strip_list_marker(content["text"])
                    changed = True
        return type(plan).model_validate(data) if changed else plan

    def _insert_blocks_adapter(self, instruction: str) -> TypeAdapter[Any]:
        # A checklist forces TODO items; a requested heading keeps its HEADER.
        if not self._requires_checklist_todo_schema(instruction):
            return INSERT_BLOCKS_BATCH_ADAPTER
        if self._requests_heading(instruction):
            return CHECKLIST_WITH_HEADING_INSERT_BLOCKS_BATCH_ADAPTER
        return CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER

    def _mixed_operations_adapter(self, instruction: str) -> TypeAdapter[Any]:
        if not self._requires_checklist_todo_schema(instruction):
            return MIXED_OPERATIONS_BATCH_ADAPTER
        if self._requests_heading(instruction):
            return CHECKLIST_WITH_HEADING_MIXED_OPERATIONS_BATCH_ADAPTER
        return CHECKLIST_MIXED_OPERATIONS_BATCH_ADAPTER

    @staticmethod
    def _requests_heading(instruction: str) -> bool:
        normalized_instruction = instruction.casefold()
        return any(term in normalized_instruction for term in HEADING_INTENT_TERMS)

    def _requires_checklist_todo_schema(
        self,
        instruction: str,
    ) -> bool:
        normalized_instruction = instruction.casefold()

        return any(
            term in normalized_instruction
            for term in CHECKLIST_INTENT_TERMS
        )

    async def _generate(
        self,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int,
        response_schema: dict[str, Any],
    ) -> LLMGenerationResult:
        logger.info(
            "modification_planner_generation_started "
            "stage=%s provider=%s model=%s",
            stage,
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
        )
        try:
            return await self.llm_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_new_tokens=max_new_tokens,
                response_schema=response_schema,
            )
        except Exception as exc:
            logger.warning(
                "modification_planner_generation_failed "
                "stage=%s provider=%s model=%s "
                "error_type=%s",
                stage,
                self.llm_provider.provider_name,
                self.llm_provider.model_name,
                type(exc).__name__,
            )
            raise
    def _serialize_context(
        self,
        context: AiPageContext,
        instruction: str = "",
    ) -> dict[str, Any]:
        # Kế hoạch trang dài (E3/E4): the compact context (D.2), or only the part
        # the sentence needs when the Page is over the prompt budget.
        return window_context(context, instruction, self._context_budget_tokens())

    def _context_budget_tokens(self) -> int:
        # E2 (2026-11-06): the fixed part of a generation prompt (system prompt,
        # sentence, schema) is ~1.850 tokens; the output keeps 1.200.
        num_ctx = getattr(self.llm_provider, "_num_ctx", None) or DEFAULT_NUM_CTX
        return max(MIN_CONTEXT_BUDGET_TOKENS, num_ctx - GENERATION_MAX_NEW_TOKENS - PROMPT_FIXED_TOKENS)

    def _combine_usage(
        self,
        first: LLMTokenUsage | None,
        second: LLMTokenUsage | None,
    ) -> LLMTokenUsage | None:
        if first is None or second is None:
            return None
        return LLMTokenUsage(
            prompt_tokens=(
                first.prompt_tokens
                + second.prompt_tokens
            ),
            completion_tokens=(
                first.completion_tokens
                + second.completion_tokens
            ),
            total_tokens=(
                first.total_tokens
                + second.total_tokens
            ),
        )
    def _raise_invalid_response(
        self,
        exc: Exception,
    ) -> NoReturn:
        logger.warning(
            "modification_planner_invalid_response "
            "provider=%s model=%s "
            "error_type=%s",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
            type(exc).__name__,
        )
        raise InvalidLLMResponseError(
            "Modification planner response is invalid."
        ) from exc
