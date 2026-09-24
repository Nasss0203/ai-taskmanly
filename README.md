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
- `OLLAMA_TIMEOUT_SECONDS=60`
- `AI_INTERNAL_TOKEN=<service-to-service secret>`

The development fallback token is rejected when `APP_ENV=production`.

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
```

Writing accepts an explicit action (`IMPROVE`, `SHORTEN`, `EXPAND`,
`SUMMARIZE`, `TRANSLATE`, or `CONTINUE`) and text. `TRANSLATE` also requires
`targetLanguage`. The internal provider is selected from configuration and the
default development path calls Ollama over HTTP.

## Run the tests

```bash
python -m pytest
```

The tests inject fake providers or use mocked HTTP. They do not call Ollama,
load model weights, download a model, or require a GPU.

## Legacy compatibility

`POST /api/v1/assistant` is frozen for compatibility. It still resolves
`Qwen/Qwen3-1.7B` through the legacy in-process Transformers provider with
`local_files_only=True`, so calling it requires the model in the local Hugging
Face cache. New features belong under `/internal/v1` and do not use this legacy
provider.
