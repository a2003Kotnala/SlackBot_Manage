# Running ZManage

This project should run against Supabase Postgres. You do not need SQL Server or the Microsoft ODBC driver.

## Prerequisites

- Python virtual environment available at `venv/`
- Dependencies installed from `requirements.txt`
- A Supabase Postgres connection string in `SUPABASE_DB_URL`
- A valid Slack bot token in `SLACK_BOT_TOKEN`
- A valid Slack signing secret in `SLACK_SIGNING_SECRET` if you want to receive Slack requests

## Required environment variables

Use `.env` with values like:

```env
APP_ENV=development
SUPABASE_DB_URL=postgresql://postgres.your-project-ref:your-db-password@aws-0-region.pooler.supabase.com:5432/postgres
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_APP_TOKEN=xapp-your-app-token
OPENAI_API_KEY=your_openai_key
```

Notes:

- `SUPABASE_DB_URL` is the preferred DB variable.
- For local development, prefer the Supabase Session pooler connection string from the dashboard `Connect` panel.
- `SLACK_BOT_TOKEN` is the preferred Slack token variable.
- The API will still start even if Slack credentials are wrong, but Slack endpoints will return an error when called.

## Install dependencies

From the project root:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run the API

From the project root:

```powershell
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH = "."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The app will be available at:

- `http://127.0.0.1:8000`
- Health check: `http://127.0.0.1:8000/health`

## Run database migrations

If you add Alembic revisions later, run:

```powershell
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH = "."
alembic upgrade head
```

## If startup fails

- `ModuleNotFoundError: No module named 'app'`
  Set `PYTHONPATH` to `.` before running the app.

- `invalid_auth`
  Your Slack bot token is invalid. Replace `SLACK_BOT_TOKEN` with a real bot token from your Slack app.

- Supabase connection errors
  Verify the password, host, and port. If the direct database host fails, use the Supabase Session pooler connection string instead.
