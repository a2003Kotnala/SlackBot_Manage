# ZManage Structure

This project is a FastAPI backend that takes Slack huddle notes, extracts structured action items, creates a draft canvas, and stores workflow state in Postgres. Supabase is the recommended hosted Postgres provider for this repo.

## Top level

- `app/`: application source code
- `app/api/`: HTTP route layer
- `app/config.py`: environment settings and database URL resolution
- `app/db/`: SQLAlchemy models, engine, session, and Alembic migrations
- `app/domain/`: business schemas and domain services
- `app/integrations/`: external client wrappers such as Slack and OpenAI
- `app/slack/`: Slack Bolt initialization, handlers, and Slack-specific services
- `scripts/`: local helper scripts
- `tests/`: automated tests
- `diagrams/`: reference diagrams and architecture images
- `.env.example`: example environment variables
- `alembic.ini`: Alembic configuration shell; the actual DB URL is injected from app settings

## Request and data flow

1. Slack hits `/slack/commands` or `/slack/interactions` in `app/api/routes/`.
2. `app/slack/bolt_app.py` lazily creates the Slack Bolt app and registers handlers.
3. `app/slack/handlers/commands.py` handles `/zmanage`.
4. `app/slack/services/source_resolver.py` reads Slack files and creates a `Source` DB record.
5. `app/domain/services/extraction_service.py` extracts structured information from the source content.
6. `app/domain/services/draft_service.py` creates a Slack draft canvas and persists a `Draft` plus `ExtractedItem` rows.

## Folder details

### `app/api/`

- `routes/health.py`: health-check endpoint
- `routes/slack_commands.py`: Slack slash-command entrypoint
- `routes/slack_interactions.py`: Slack interaction entrypoint

### `app/db/`

- `base.py`: SQLAlchemy engine and declarative base
- `session.py`: `SessionLocal` factory used by services
- `models/`: persistence models for the relational schema
- `migrations/`: Alembic migration environment and revisions
- `repositories/`: intended place for data-access abstractions, currently mostly empty

Current DB models:
- `models/user.py`: Slack-linked user records
- `models/source.py`: imported source material such as huddle notes
- `models/draft.py`: generated action-plan drafts
- `models/extracted_item.py`: extracted decisions, action items, questions, and related items
- `models/share.py`: records of where a draft was shared

### `app/domain/`

- `schemas/extraction.py`: Pydantic schemas for extracted output
- `services/extraction_service.py`: extraction workflow
- `services/draft_service.py`: draft creation and DB persistence
- `services/canvas_composer.py`: builds Slack canvas content
- `models/`: duplicate ORM-style models that overlap with `app/db/models/`; these should likely be removed or consolidated later

### `app/integrations/`

- `slack_client.py`: lower-level Slack API wrapper
- `openai_client.py`: OpenAI integration wrapper

### `app/slack/`

- `bolt_app.py`: Slack Bolt app creation and handler registration
- `handlers/`: slash commands, shortcuts, modals, and app home listeners
- `services/source_resolver.py`: Slack-specific source discovery logic
- `services/canvas_service.py`: Slack canvas operations
- `services/share_service.py`: Slack sharing operations

## Supabase guidance

- Use `SUPABASE_DB_URL` as the primary SQLAlchemy connection string.
- Keep using SQLAlchemy models and Alembic migrations; Supabase is the hosted Postgres provider, not a separate ORM layer.
- `SLACK_TOKEN` is accepted as a fallback env name for local compatibility, but `SLACK_BOT_TOKEN` is the preferred name.
