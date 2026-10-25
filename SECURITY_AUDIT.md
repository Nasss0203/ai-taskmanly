# Pre-M0 security audit

## Scope and baseline

Only `ai-taskmanly` was inspected/edited. Initial `git status --short` was empty;
the baseline suite had 284 passing tests. No project `AGENTS.md`,
`quy-trinh-thuc-hien.md`, `page-resolution-plan-v2.md`, `intent-detection.md` or
`intent_cases.jsonl` was available locally. Tests use fake providers/mocked HTTP;
no real-model accuracy is claimed.

The implementation order was token validation, legacy authentication, request
limits, private-content logging, obsolete planner prompts, then source-backed
Page editing intent. Each confirmed vulnerability was reproduced with focused
tests before its fix; targeted checks followed each change.

## Decisions

1. **Token policy.** Development/production reject missing/blank/placeholder
   secrets, fewer than 32 printable ASCII characters, whitespace, fewer than
   12 distinct characters, and repeated patterns. This format check cannot
   establish entropy: generate at least 32 random bytes, then encode as hex or
   base64url. `APP_ENV=test` permits fixture secrets. `SecretStr` is applied
   before validation so serialized validation errors also redact secrets.
   The existing constant-time header comparison is unchanged. The real `.env`
   was not edited; local configuration requires an `AI_INTERNAL_TOKEN` update.

2. **Legacy assistant.** Repository references comprise router registration,
   route/characterization tests and an explicit README compatibility promise.
   No external consumer was inferred. Keeping the route behind the existing
   internal-token dependency preserves compatibility while closing anonymous
   access; no assistant source files were removed.

3. **Input budgets.** Shared Pydantic validators preserve field names,
   optionality and values, returning 422 without truncation. Limits are
   documented in README. The default `ollama_num_ctx=16384` and output caps
   (Writing 1000, Composition 4000, Planner 1200, Intent 300) informed the
   ceilings. UTF-8 bytes avoid assuming one tokenization ratio for Vietnamese
   and English. HTTP stream limits also bound ignored/unknown fields and
   prevent deeply nested JSON from reaching the decoder. These are resource
   ceilings, not a claim that every custom model/window can fit every input.

4. **Logging.** Composition no longer logs raw model text, Pydantic exception
   strings or semantic exception strings (which contain model-authored refs).
   Semantic detail still goes to the existing private repair call, not logs.
   The provider's HTTP-error body log was also removed because an upstream
   error can echo private input. Safe provider/model/error-type/status/latency
   metadata and public error responses remain available.

5. **Planner prompt audit.** The service imports exactly five builders:
   `build_modification_planner_route_prompt`,
   `build_insert_blocks_generation_prompt`,
   `build_create_database_rows_generation_prompt`,
   `build_mixed_operations_generation_prompt`, and
   `build_need_more_context_generation_prompt`. Their five system prompts,
   including the intentional NEED_MORE_CONTEXT branch, remain unchanged.
   No dynamic import/getattr reference to planner prompts exists. The old
   single-stage `SYSTEM_PROMPT`, `REPAIR_SYSTEM_PROMPT`,
   `build_modification_planner_prompt` and
   `build_modification_planner_repair_prompt` were only referenced by 14 direct
   obsolete prompt tests. Those definitions/tests were removed. Remaining
   prompt AST (including string values) was compared before/after cleanup.
   Existing service/schema/semantic/HTTP tests still cover the current planner.

6. **Page edit evidence.** A verb occurring anywhere in a sentence was not
   sufficient evidence: informational/negated sentences can mention editing.
   Evidence now requires an affirmative command clause. Broader recognized
   commands retain the full original source when the narrow reference parser
   cannot extract a clause. Model instructions are never the fallback. Explicit
   titles, current-page/unresolved semantics, strict output fields, rejection
   of fabricated `pageId` and applicable one-retry behavior remain intact.
   Required read/view negatives, supported fabricated TEXT insertion, all five
   required positive examples, broader commands, negation, title-contained
   edit words, and HTTP behavior are covered by automated regressions.

## Operational notes

- Update `AI_INTERNAL_TOKEN` in the local environment before starting the app;
  do not copy the intentionally invalid `.env.example` placeholder as a secret.
- Callers of the legacy assistant must now provide the internal token.
- Conservative intent extraction can require clarification for unrecognized
  phrasing. It never grants execution authority; NestJS still owns that boundary.
- No M0 router, resolution milestone, database migration or Page mutation was
  implemented. No dependency/tooling changes were introduced.

## Verification

- Baseline: 284 passed.
- Final targeted suite (configuration, authentication, input limits, all four
  capabilities and Ollama HTTP mocks): 412 passed, 0 failed, 0 skipped.
- Full required command, `.\.venv\Scripts\python.exe -m pytest -q`:
  415 passed, 0 failed, 0 skipped. Compared with baseline, 145 regression cases
  were added and 14 obsolete single-stage prompt tests were removed.
- HTTP checks cover legacy 401/authorized 200, existing internal contracts,
  invalid-input 422 without LLM calls, and read-only intent output safety.
- One pre-existing Starlette/httpx deprecation warning remains. No configured
  lint/type-check tool was found; none was added.
- `.env` configuration was validated without printing its contents and failed
  the new token policy. This is an expected operational prerequisite.
- Git index remains unchanged. No commit/push was performed.
