# FollowThru

FollowThru is a FastAPI backend that turns Slack huddle notes, DM transcript
text, transcript files, and supported meeting recording links into structured
Slack action canvases.

## Launch Scope

- PostgreSQL-first workflow storage with Alembic migrations
- Slack slash-command and app-mention handling
- FollowThru chat API with persisted sessions and messages
- Async DM ingestion jobs with idempotent job creation and duplicate-safe retries
- Transcript file ingestion for `.txt`, `.md`, `.csv`, `.tsv`, `.srt`, `.vtt`,
  `.log`, and `.docx`
- Zoom recording-link ingestion with provider isolation and transcript-first
  fallback before media transcription
- FFmpeg-based media normalization plus OpenAI-compatible transcription support
- Voice-command API that accepts speech-to-text transcripts and drives canvas generation
- Deterministic extraction fallback plus optional Gemini/OpenAI-compatible LLM support
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

## DM Intake

In a DM with FollowThru, you can now:

- paste transcript text directly
- upload transcript files
- paste a supported Zoom recording link

DM work is accepted immediately and processed in background jobs so Slack request
handlers stay fast. Progress and completion updates are posted back into the DM.

Supported DM flows in this repo today:

- transcript text to extraction to canvas draft
- transcript file to parsing to extraction to canvas draft
- Zoom link to transcript fetch or media transcription to canvas draft

## Background Processing

Slack request handlers acknowledge quickly and hand work to an ingestion job.
The job pipeline currently covers:

- source classification and validation
- idempotent job creation for duplicate-safe DM retries
- transcript parsing and transcript cleaning
- provider-isolated Zoom link handling
- optional FFmpeg audio normalization for media sources
- OpenAI-compatible transcription for media when no transcript is available
- meeting intelligence extraction and Slack canvas rendering

The current worker is an in-process threaded queue designed to keep business
logic out of the Slack transport layer. The DB models and state machine are
ready for a future Redis-backed worker upgrade without changing the ingestion
interfaces.

## Local PostgreSQL Setup

Start PostgreSQL with Docker Compose:

```powershell
docker compose up -d postgres
```

Create `.env` from `.env.example`, then run:

```powershell
.\myenv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH="."
alembic upgrade head
python scripts/dev.py
```

The default local API URL is `http://127.0.0.1:8010`.

## AI Provider Notes

FollowThru keeps the existing Gemini/OpenAI-compatible behavior:

- if Gemini-style OpenAI-compatible settings are present, those are used
- if OpenAI-compatible settings are present, those are used
- transcription settings can reuse the same key/base URL/model or be overridden separately
- deterministic extraction remains available when no compatible API key is configured

For media transcription, make sure `ffmpeg` is installed and available on `PATH`
or set `FFMPEG_BINARY`.

Relevant environment variables include:

- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_API_KEY`, `GEMINI_API_KEY`, or `OPENAI_API_KEY`
- `LLM_MODEL`
- `TRANSCRIPTION_BASE_URL`
- `TRANSCRIPTION_API_KEY`
- `TRANSCRIPTION_MODEL`
- `FOLLOWTHRU_JOB_EXECUTION_MODE`
- `FOLLOWTHRU_MAX_JOB_RETRIES`
- `FOLLOWTHRU_DOWNLOAD_TIMEOUT_SECONDS`
- `FOLLOWTHRU_MAX_DOWNLOAD_BYTES`
- `FFMPEG_BINARY`

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
- DM ingestion jobs, Zoom link support, transcript-file parsing, and cleaner
  canvas rendering are now part of the core workflow.
- Gemini and OpenAI-compatible key paths both remain supported.
- A launch checklist is available at [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md).
