from __future__ import annotations
import logging
from time import perf_counter
from typing import Any, NoReturn
from pydantic import TypeAdapter, ValidationError
from app.core.exceptions import InvalidLLMResponseError
from app.llm.base import (
    LLMGenerationResult,
    LLMProvider,
    LLMTokenUsage,
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
NEED_MORE_CONTEXT_DETAILS_ADAPTER = TypeAdapter(
    ModificationNeedMoreContextDetails,
)
ROUTER_MAX_NEW_TOKENS = 256
GENERATION_MAX_NEW_TOKENS = 1200

CHECKLIST_INTENT_TERMS = (
    "checklist",
    "check list",
    "task list",
    "todo",
    "to-do",
)
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
        context_payload = self._serialize_context(
            request.context,
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
            validate_modification_plan_semantics(
                plan,
                request.context,
            )
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
        if total_usage is None:
            return ModificationPlannerResponse(
                result=plan,
                provider=self.llm_provider.provider_name,
                model=self.llm_provider.model_name,
            )
        return ModificationPlannerResponse(
            result=plan,
            provider=self.llm_provider.provider_name,
            model=self.llm_provider.model_name,
            usage=ModificationPlannerUsage(
                prompt_tokens=total_usage.prompt_tokens,
                completion_tokens=(
                    total_usage.completion_tokens
                ),
                total_tokens=total_usage.total_tokens,
            ),
        )
    async def _generate_route(
        self,
        request: ModificationPlannerRequest,
        context_payload: dict[str, Any],
    ) -> LLMGenerationResult:
        system_prompt, user_prompt = (
            build_modification_planner_route_prompt(
                instruction=request.instruction,
                context=context_payload,
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
                )
            )
            if self._requires_checklist_todo_schema(
                request.instruction,
            ):
                response_schema = (
                    CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER.json_schema()
                )
            else:
                response_schema = (
                    INSERT_BLOCKS_BATCH_ADAPTER.json_schema()
                )
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
                )
            )
            if self._requires_checklist_todo_schema(
                request.instruction,
            ):
                response_schema = (
                    CHECKLIST_MIXED_OPERATIONS_BATCH_ADAPTER.json_schema()
                )
            else:
                response_schema = (
                    MIXED_OPERATIONS_BATCH_ADAPTER.json_schema()
                )
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
            if self._requires_checklist_todo_schema(
                request.instruction,
            ):
                batch = (
                    CHECKLIST_INSERT_BLOCKS_BATCH_ADAPTER.validate_python(
                        raw_result,
                    )
                )
            else:
                batch = (
                    INSERT_BLOCKS_BATCH_ADAPTER.validate_python(
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
            if self._requires_checklist_todo_schema(
                request.instruction,
            ):
                batch = (
                    CHECKLIST_MIXED_OPERATIONS_BATCH_ADAPTER.validate_python(
                        raw_result,
                    )
                )
            else:
                batch = (
                    MIXED_OPERATIONS_BATCH_ADAPTER.validate_python(
                        raw_result,
                    )
                )

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
    ) -> dict[str, Any]:
        return context.model_dump(
            mode="json",
            exclude_unset=True,
        )
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
            "error_type=%s error=%s",
            self.llm_provider.provider_name,
            self.llm_provider.model_name,
            type(exc).__name__,
            str(exc),
        )
        raise InvalidLLMResponseError(
            "Modification planner response is invalid."
        ) from exc
