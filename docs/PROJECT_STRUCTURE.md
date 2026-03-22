# FollowThru Structure

FollowThru is a FastAPI backend for turning Slack notes, chat prompts, and
voice transcripts into action canvases backed by PostgreSQL.

## Top Level

- `app/`: application source
- `app/api/`: HTTP routes
- `app/config.py`: runtime configuration
- `app/db/`: SQLAlchemy models, sessions, and Alembic migrations
- `app/domain/`: schemas and workflow services
- `app/integrations/`: OpenAI-compatible and Slack wrappers
- `app/slack/`: Bolt registration and Slack-specific handlers
- `scripts/`: local development helpers
- `docs/`: runbooks and release notes
- `tests/`: unit coverage

## Main Runtime Surfaces

- `GET /health`
- `GET /db-health`
- `GET /api/v1/followthru/capabilities`
- `POST /api/v1/followthru/chat`
- `POST /api/v1/followthru/voice-command`
- `POST /api/v1/workflows/preview`
- `POST /api/v1/workflows/process-text`
- `POST /slack/commands`
- `POST /slack/interactions`

## Important Modules

### `app/api/`

- `routes/followthru.py`: chat, voice-command, and capability endpoints
- `routes/workflows.py`: preview and text-processing workflow APIs
- `routes/health.py`: liveness and readiness
- `routes/slack_commands.py`: Slack slash-command bridge
- `routes/slack_interactions.py`: Slack interaction bridge

### `app/db/`

- `models/source.py`: raw source capture, including `voice`
- `models/draft.py`: generated draft metadata
- `models/extracted_item.py`: normalized extracted entities
- `models/chat_session.py`: persisted FollowThru chat sessions
- `models/chat_message.py`: persisted FollowThru chat messages
- `migrations/versions/20260319_0001_initial_schema.py`: initial workflow schema
- `migrations/versions/20260323_0002_followthru_chat_and_indexes.py`: chat persistence and indexes

### `app/domain/`

- `schemas/extraction.py`: structured extraction contract
- `schemas/workflow.py`: preview/process-text request and response models
- `schemas/followthru.py`: chat and voice-command request and response models
- `services/extraction_service.py`: LLM-backed or deterministic extraction
- `services/canvas_composer.py`: Slack canvas markdown generation
- `services/draft_service.py`: draft persistence and optional Slack publication
- `services/followthru_service.py`: FollowThru chat, voice-command, session persistence, and orchestration

### `app/integrations/`

- `openai_client.py`: OpenAI-compatible extraction and chat completion wrapper
- `slack_client.py`: Slack Web API wrapper for canvases and file lookup

### `app/slack/`

- `bolt_app.py`: Bolt app bootstrap
- `handlers/commands.py`: `/followthru`, `/zmanage`, and `app_mention` registration
- `services/source_resolver.py`: source persistence helpers for Slack-originated content
