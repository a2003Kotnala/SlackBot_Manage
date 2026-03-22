# Running FollowThru

## Prerequisites

- Python virtual environment available at `venv/`
- Dependencies installed from `requirements.txt`
- PostgreSQL reachable from `DATABASE_URL`

Slack and an LLM provider are optional for local development:

- Without Slack credentials, Slack endpoints return `503`, but the API still starts.
- Without an LLM key, extraction and chat fall back to deterministic behavior.

## Environment

Use `.env.example` as the source of truth. The intended local database is:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/followthru
```

Start PostgreSQL locally with:

```powershell
docker compose up -d postgres
```

## Install And Migrate

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH="."
alembic upgrade head
```

## Run The API

```powershell
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH="."
python scripts/dev.py
```

The default local URL is `http://127.0.0.1:8010`.

## Slack Setup

Configure these Slack app values:

- Slash command: `/followthru`
- Request URL: `https://<public-host>/slack/commands`
- Interactivity Request URL: `https://<public-host>/slack/interactions`
- Event subscription for `app_mention`

Reinstall the Slack app after changing commands or event subscriptions.

## API Smoke Tests

```powershell
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/api/v1/followthru/capabilities
```

```powershell
curl -X POST http://127.0.0.1:8010/api/v1/followthru/chat `
  -H "Content-Type: application/json" `
  -d "{\"message\":\"help\",\"user_id\":\"demo-user\"}"
```

```powershell
curl -X POST http://127.0.0.1:8010/api/v1/followthru/voice-command `
  -H "Content-Type: application/json" `
  -d "{\"transcript\":\"preview these notes: Decision: Ship pilot. Action: Prepare demo @maya 2026-03-25\",\"user_id\":\"voice-user\"}"
```

## Quality Checks

```powershell
python -m black app tests scripts
python -m ruff check app tests
python -m pytest tests\unit
```

## Common Failures

- `ModuleNotFoundError: No module named 'app'`
  Set `PYTHONPATH` to `.`
- `connection refused` or `password authentication failed`
  Verify the local PostgreSQL container and `DATABASE_URL`
- Slack `dispatch_failed`
  Check the public Request URL and reinstall the Slack app
- Slack says `/followthru` is not a valid command
  Create the slash command in Slack App settings and reinstall
- AI request failures
  Leave `LLM_API_KEY` empty for deterministic behavior, or verify the provider URL, model, and key
