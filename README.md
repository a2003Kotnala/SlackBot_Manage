# ZManage

ZManage is a FastAPI backend that turns Slack huddle notes and manually supplied meeting text into structured action-plan drafts.

## What Is Implemented

- Slack command entrypoints through FastAPI and Slack Bolt
- Rule-based extraction fallback for local/demo mode
- Optional AI-powered extraction through any OpenAI-compatible API
- Draft canvas composition and persistence to SQLite or PostgreSQL
- SQLite-first local development with PostgreSQL/Supabase kept for production
- Preview and processing APIs for non-Slack demos
- Alembic migration baseline, tests, lint, format, and pre-commit config

## Workflow Phases

1. Source capture
   Slack canvas lookup or direct text submission
2. Extraction
   Structured parsing of decisions, action items, questions, and risks
3. Draft generation
   Canvas markdown assembly and draft persistence
4. Publication
   Optional Slack canvas upload when credentials and channel context exist
5. Operability
   Health checks, migration support, tests, and code-quality tooling

## Stack

- FastAPI
- Slack Bolt for Python
- SQLAlchemy
- Alembic
- PostgreSQL
- SQLite (local development)
- OpenAI-compatible LLM API (optional)

## API Endpoints

- `GET /health`
- `GET /db-health`
- `POST /api/v1/workflows/preview`
- `POST /api/v1/workflows/process-text`
- `POST /slack/commands`
- `POST /slack/interactions`

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Configure environment variables in `.env` using `.env.example`.
   For local work, `DATABASE_URL=sqlite:///./zmanage.db` is enough.
   Leave `GEMINI_API_KEY` empty to use rule-based extraction only, or set
   `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, and optionally override `LLM_MODEL`.
4. Run migrations:

```powershell
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH="."
alembic upgrade head
```
5. Run the API:

```powershell
$env:PYTHONPATH="."
python scripts/dev.py
```

## Local Demo Without Slack Or An LLM

Use the preview endpoint with raw text:

```powershell
curl -X POST http://127.0.0.1:8010/api/v1/workflows/preview `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"Decision: Ship the pilot. Action: Prepare demo @maya 2026-03-20\"}"
```

## Database And AI Config

- Local development defaults to SQLite through `DATABASE_URL=sqlite:///./zmanage.db`.
- PostgreSQL or Supabase stays the production target.
- `DATABASE_URL` is preferred over `SUPABASE_DB_URL` when both are present.
- Gemini is the default local AI example through Google’s OpenAI-compatible endpoint.
- `LLM_API_KEY`, `LLM_MODEL`, and `LLM_BASE_URL` support OpenAI-compatible providers.
- `GEMINI_API_KEY` is accepted as a convenience alias for `LLM_API_KEY`.
- `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_TIMEOUT_SECONDS` still work as
  backward-compatible aliases.
- Apply migrations with:

```powershell
alembic upgrade head
```

## Tooling

- Format: `black .`
- Lint: `ruff check .`
- Tests: `python -m pytest`
- Hooks: `pre-commit install`
