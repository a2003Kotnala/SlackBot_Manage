# ZManage

ZManage is a FastAPI backend that integrates with Slack to turn huddle notes and related Slack content into structured action-plan drafts.

## Stack

- FastAPI
- Slack Bolt for Python
- SQLAlchemy
- Alembic
- PostgreSQL

## Local Setup

1. Create and activate the virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Configure environment variables in `.env`:

```env
APP_ENV=development
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/ZManage
SLACK_BOT_TOKEN=your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_APP_TOKEN=your-app-token
OPENAI_API_KEY=
```

4. Run the API:

```powershell
$env:PYTHONPATH="."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

## Health Checks

- App health: `GET /health`
- Database health: `GET /db-health`

## Database

The project is currently set up for PostgreSQL. For local development, create a database named `ZManage` in pgAdmin and point `DATABASE_URL` to it.

Alembic is configured under `app/db/migrations`. This repo does not yet include an initial migration file, so you will need to generate one before applying schema changes.

## Project Notes

- Slack initialization is lazy, so invalid Slack credentials should not prevent the API from starting.
- `SLACK_BOT_TOKEN` is the preferred Slack token variable.
- `PYTHONPATH="."` is required when running the project in the current layout.
