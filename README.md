# Taskmanly AI Service

Taskmanly keeps business authority in NestJS and uses this FastAPI service only
for AI orchestration. The current foundation supports this new flow:

```text
Next.js → NestJS → FastAPI internal API → Ollama → Qwen
```

NestJS authenticates users, enforces workspace permissions and domain rules,
and passes only the content required for an AI operation. FastAPI does not
connect to the Taskmanly business database or mutate business entities.

## Python version

Use Python 3.11.x. The source requires Python 3.10 or newer, and Python 3.11 is
compatible with every pinned direct dependency in this repository.

Do not reuse or commit an existing `.venv`. The directory is already ignored
by `.gitignore`.

## Create the environment

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

macOS or Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`requirements.txt` contains direct production dependencies. The legacy
Transformers dependencies remain while the compatibility endpoint exists.
`requirements-dev.txt` adds the test runner.

## Configuration

Copy the safe keys from `.env.example` into the deployment environment and set
a real `AI_INTERNAL_TOKEN`. Important settings are:

- `LLM_PROVIDER=ollama`
- `OLLAMA_BASE_URL=http://localhost:11434`
- `OLLAMA_MODEL=qwen3:4b`
- `OLLAMA_TIMEOUT_SECONDS=240` (whole streamed request; keep it below the
  backend's `AI_SERVICE_TIMEOUT_MS`)
- `OLLAMA_IDLE_TIMEOUT_SECONDS=60` (longest silence while streaming)
- `AI_INTERNAL_TOKEN=<service-to-service secret>`

Both development and production require an explicitly configured token:
at least 32 printable ASCII characters, at least 12 distinct characters,
no whitespace, repeated pattern or placeholder text. Generate at least 32
random bytes and encode as hex or base64url; never use a human-written example.
Invalid settings fail before providers initialize. Only `APP_ENV=test` permits
short fixture secrets or an omitted token. Validation errors redact the token.
For a deterministic local smoke test without Ollama, set `LLM_PROVIDER=fake`.

## Run the API

```bash
python -m uvicorn app.main:app --reload
```

The legacy public liveness endpoint is:

```text
GET http://127.0.0.1:8000/api/v1/health
```

It does not initialize or check the legacy Qwen model.

## Internal API

NestJS calls internal routes with:

```text
X-Internal-Service-Token: <AI_INTERNAL_TOKEN>
```

Implemented internal routes:

```text
GET  /internal/v1/health
POST /internal/v1/writing
POST /internal/v1/page-composition
POST /internal/v1/modification-planner
POST /internal/v1/page-intent
POST /internal/v1/intent
```

Writing accepts an explicit action (`IMPROVE`, `SHORTEN`, `EXPAND`,
`SUMMARIZE`, `TRANSLATE`, or `CONTINUE`) and text. `TRANSLATE` also requires
`language` (`targetLanguage` remains accepted as an input alias). The response
contains `result`. The internal provider is selected from configuration and the
default development path calls Ollama over HTTP.

AI inputs are rejected with HTTP 422 rather than truncated:

- Writing text: 1–8000 characters, nonblank.
- Composition, Planner, Page Intent and M0 Intent instructions: 1–4000 characters, nonblank.
- M0 optional `selectedText`: 1–8000 characters, nonblank when supplied;
  optional caller `currentPageId`: 1–128 characters, nonblank when supplied.
- Structured context: at most 8000 bytes of compact UTF-8 JSON, 12 container
  levels and 1000 value/container nodes (keys also count toward byte size).
- Combined instruction/context input: at most 10000 bytes of compact UTF-8
  JSON, including field names/wrappers; Writing and Page Intent apply this ceiling
  to their text/instruction JSON string. M0 Intent checks the whole input object.
  Unicode and escaped text can reach
  the byte ceiling before the character ceiling.
- The five AI HTTP endpoints accept at most 65536 body bytes and 13 JSON
  container levels, enforced on streamed bodies before JSON decoding.

These resource ceilings are based on the default 16384-token context window
and existing generation budgets. They do not replace model-specific token
accounting, particularly for smaller custom context windows or repair calls.
Composition's optional context and existing JSON field/response names are
preserved. Send only the context required for the operation; oversized input
must be reduced by the caller without silently changing an editing instruction.

Page Intent only emits editing instructions backed by the original request.
Read/view/search requests cannot acquire an editing action from model output;
uncertain language requires clarification. FastAPI creates structured drafts
only. NestJS remains responsible for Page resolution, permissions and execution.

M0 Intent classifies a natural-language request into `CREATE_PAGE`,
`MODIFY_PAGE`, `WRITING`, `OTHER` or `UNCLEAR`. It accepts `instruction`,
optional `selectedText` and optional caller `currentPageId`. It returns the
existing `result`/`provider`/`model` envelope; `result` contains `intent`,
`writingAction`, `language` and code-owned `needsClarification`.
Classification never calls Writing, Page Composition, Page Intent or Planner.
The model receives only a boolean current-Page indicator, never the caller ID.
See [M0 Intent contract and verification](M0_INTENT_ROUTER.md) before integration.

## Run the tests

```bash
python -m pytest
```

The tests inject fake providers or use mocked HTTP. They do not call Ollama,
load model weights, download a model, or require a GPU.

## Legacy compatibility

`POST /api/v1/assistant` is retained for the documented compatibility contract
and now requires the same `X-Internal-Service-Token` header as internal routes.
Requests without a valid token return 401 before invoking the legacy service.
It still resolves
`Qwen/Qwen3-1.7B` through the legacy in-process Transformers provider with
`local_files_only=True`, so calling it requires the model in the local Hugging
Face cache. New features belong under `/internal/v1` and do not use this legacy
provider.
