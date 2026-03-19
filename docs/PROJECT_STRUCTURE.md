# ZManage Structure

ZManage is a FastAPI backend that ingests Slack huddle notes or direct meeting text, extracts structured execution data, creates draft action canvases, and stores workflow state in SQLite locally and PostgreSQL in production.

## Top Level

- `app/`: application source code
- `app/api/`: HTTP route layer
- `app/config.py`: environment settings and integration flags
- `app/db/`: SQLAlchemy engine, models, sessions, and Alembic migrations
- `app/domain/`: extraction schemas and workflow services
- `app/integrations/`: Slack and OpenAI-compatible LLM client wrappers
- `app/slack/`: Slack Bolt bootstrap, handlers, and source resolution
- `scripts/`: local development helpers
- `tests/`: unit tests
- `docs/`: project and running documentation

## Workflow Phases

1. Source capture
   Slack command payloads or direct text API requests enter through `app/api/routes/`.
2. Source normalization
   `app/slack/services/source_resolver.py` persists Slack canvases or manual text as `Source` rows.
3. Extraction
   `app/domain/services/extraction_service.py` uses a configured OpenAI-compatible LLM and deterministic parsing otherwise.
4. Draft generation
   `app/domain/services/canvas_composer.py` builds canvas markdown and `app/domain/services/draft_service.py` persists the draft and extracted items.
5. Publication
   Slack canvas upload is attempted only when credentials, channel context, and the publish flag are available.

## API Surface

- `GET /health`: service metadata and integration readiness
- `GET /db-health`: database connectivity probe
- `POST /api/v1/workflows/preview`: extract and render a draft without persistence
- `POST /api/v1/workflows/process-text`: persist a manual-text workflow
- `POST /slack/commands`: Slack slash command entrypoint
- `POST /slack/interactions`: Slack interaction entrypoint

## Folder Details

### `app/api/`

- `routes/health.py`: liveness and DB checks
- `routes/workflows.py`: preview and process-text workflow APIs
- `routes/slack_commands.py`: Slack slash-command bridge
- `routes/slack_interactions.py`: Slack interactions bridge

### `app/db/`

- `base.py`: SQLAlchemy engine and declarative base
- `session.py`: `SessionLocal` factory
- `models/`: persistence models for users, sources, drafts, extracted items, and shares
- `migrations/`: Alembic environment and versioned schema files

### `app/domain/`

- `schemas/extraction.py`: extraction result schema
- `schemas/workflow.py`: request/response models for workflow APIs
- `services/extraction_service.py`: LLM-backed plus rule-based extraction
- `services/canvas_composer.py`: canvas markdown builder
- `services/draft_service.py`: draft persistence and optional Slack publishing

### `app/integrations/`

- `openai_client.py`: direct OpenAI-compatible HTTP integration
- `slack_client.py`: Slack SDK wrapper

### `app/slack/`

- `bolt_app.py`: Slack Bolt app creation and FastAPI adapter
- `handlers/commands.py`: `/zmanage` command workflow
- `services/source_resolver.py`: source persistence helpers
