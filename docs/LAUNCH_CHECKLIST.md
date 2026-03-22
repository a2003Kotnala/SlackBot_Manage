# FollowThru Launch Checklist

## Preflight

- `docker compose up -d postgres`
- `.env` populated from `.env.example`
- `alembic upgrade head`
- `python -m ruff check app tests`
- `python -m pytest tests\unit`

## Slack Release

- Slash command `/followthru` created
- Request URL points to `/slack/commands`
- Interactivity URL points to `/slack/interactions`
- `app_mention` event subscription enabled
- Slack app reinstalled after config changes
- Bot invited to the launch channels

## Smoke Tests

- `GET /health`
- `GET /api/v1/followthru/capabilities`
- `POST /api/v1/followthru/chat` with `{"message":"help"}`
- `POST /api/v1/followthru/voice-command` with a transcript preview request
- `/followthru help` in Slack
- `@FollowThru help` in Slack

## Production Rollback Notes

- Roll back application deploy first
- If database rollback is required, run `alembic downgrade 20260319_0001`
- Revert Slack slash command Request URL if a hotfix environment is needed
- Keep the `/zmanage` alias available during the first release window for safety
