# FollowThru

FollowThru is a FastAPI backend that turns Slack huddle notes, chat prompts, and
voice-command transcripts into structured action canvases.

## Launch Scope

- PostgreSQL-first workflow storage with Alembic migrations
- Slack slash-command and app-mention handling
- FollowThru chat API with persisted sessions and messages
- Voice-command API that accepts speech-to-text transcripts and drives canvas generation
- Deterministic extraction fallback plus optional OpenAI-compatible LLM support
- Slack canvas publishing when workspace credentials and channel context are available

## Core Endpoints

- `GET /health`
- `GET /db-health`
- `GET /api/v1/followthru/capabilities`
- `POST /api/v1/followthru/chat`
- `POST /api/v1/followthru/voice-command`
- `POST /api/v1/workflows/preview`
- `POST /api/v1/workflows/process-text`
- `POST /slack/commands`
- `POST /slack/interactions`

## Slack Surface

Primary command:

- `/followthru <notes>`
- `/followthru publish <notes>`
- `/followthru draft <notes>`
- `/followthru preview <notes>`
- `/followthru help`

Backward-compatible alias:

- `/zmanage`

Chat in Slack is also enabled through `@FollowThru` app mentions.

## Local PostgreSQL Setup

Start PostgreSQL with Docker Compose:

```powershell
docker compose up -d postgres
```

Create `.env` from `.env.example`, then run:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH="."
alembic upgrade head
python scripts/dev.py
```

The default local API URL is `http://127.0.0.1:8010`.

## Example Requests

Preview a canvas without persistence:

```powershell
curl -X POST http://127.0.0.1:8010/api/v1/workflows/preview `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"Decision: Ship pilot. Action: Prepare demo @maya 2026-03-25\"}"
```

Chat with FollowThru:

```powershell
curl -X POST http://127.0.0.1:8010/api/v1/followthru/chat `
  -H "Content-Type: application/json" `
  -d "{\"message\":\"preview these notes: Decision: Ship pilot. Action: Prepare demo @maya 2026-03-25\",\"user_id\":\"demo-user\"}"
```

Run a voice-command transcript:

```powershell
curl -X POST http://127.0.0.1:8010/api/v1/followthru/voice-command `
  -H "Content-Type: application/json" `
  -d "{\"transcript\":\"publish these notes: Decision: Ship pilot. Action: Prepare demo @maya 2026-03-25\",\"user_id\":\"voice-user\"}"
```

## Quality Checks

```powershell
python -m black app tests scripts
python -m ruff check app tests
python -m pytest tests\unit
```

## Release Notes

- PostgreSQL is now the default target database in config and docs.
- FollowThru is the primary bot identity and Slack command.
- `.env.example` contains placeholders only and no live-looking credentials.
- A launch checklist is available at [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md).
