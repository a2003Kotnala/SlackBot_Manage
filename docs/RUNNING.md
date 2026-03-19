# Running ZManage

## Prerequisites

- Python virtual environment available at `venv/`
- Dependencies installed from `requirements.txt`
- SQLite, PostgreSQL, or Supabase Postgres reachable from `DATABASE_URL` or `SUPABASE_DB_URL`

Slack and an LLM provider are optional for local development:

- Without Slack credentials, Slack endpoints will return `503`, but the app still starts.
- Without an LLM key, extraction falls back to deterministic rule-based parsing.

## Environment Variables

Use `.env` values similar to:

```env
APP_NAME=ZManage
APP_ENV=development
APP_VERSION=1.0.0
LOG_LEVEL=INFO

DATABASE_URL=sqlite:///./zmanage.db

SLACK_BOT_TOKEN=
SLACK_SIGNING_SECRET=
SLACK_APP_TOKEN=
SLACK_PUBLISH_DRAFTS=false

LLM_PROVIDER=gemini
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
GEMINI_API_KEY=
LLM_MODEL=gemini-2.5-flash
LLM_TIMEOUT_SECONDS=30
```

`LLM_API_KEY`, `LLM_MODEL`, and `LLM_BASE_URL` work with OpenAI-compatible providers.
`GEMINI_API_KEY` is also accepted and maps to the same API key setting.
`OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_TIMEOUT_SECONDS` remain valid aliases.

## Install Dependencies

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run The API

```powershell
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH = "."
python scripts/dev.py
```

The default local URL is `http://127.0.0.1:8010`.

## Run Migrations

```powershell
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH = "."
alembic upgrade head
```

## Run Quality Checks

```powershell
.\venv\Scripts\Activate.ps1
python -m black app tests scripts
python -m ruff check app tests scripts
python -m pytest
pre-commit install
```

## Demo Paths

Preview without Slack or DB writes:

```powershell
curl -X POST http://127.0.0.1:8010/api/v1/workflows/preview `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"Decision: Ship pilot. Action: Prepare demo @maya 2026-03-20\"}"
```

Process and persist manual notes:

```powershell
curl -X POST http://127.0.0.1:8010/api/v1/workflows/process-text `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"Decision: Ship pilot. Action: Prepare demo @maya 2026-03-20\",\"user_id\":\"demo-user\"}"
```

## Common Failures

- `ModuleNotFoundError: No module named 'app'`
  Set `PYTHONPATH` to `.` before running commands.
- Slack `invalid_auth`
  Replace `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` with real Slack app credentials.
- Database connection errors
  Verify the path for SQLite, or the host, port, password, and whether you are using a direct Postgres URL or Supabase pooler URL.
- AI request failures
  Leave `GEMINI_API_KEY` empty for deterministic parsing, or verify that `LLM_BASE_URL`,
  `LLM_MODEL`, and the provider key match an OpenAI-compatible endpoint.
