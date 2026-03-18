from __future__ import annotations

from slack_bolt import App
from slack_bolt.error import BoltError

from app.config import settings


_bolt_app: App | None = None
_bolt_app_error: str | None = None


def get_bolt_app() -> App:
    global _bolt_app, _bolt_app_error

    if _bolt_app is not None:
        return _bolt_app

    if not settings.slack_bot_token or not settings.slack_signing_secret:
        _bolt_app_error = "Slack credentials are not configured."
        raise RuntimeError(_bolt_app_error)

    try:
        _bolt_app = App(
            token=settings.slack_bot_token,
            signing_secret=settings.slack_signing_secret,
        )
        from app.slack.handlers.commands import register_handlers

        register_handlers(_bolt_app)
        return _bolt_app
    except BoltError as exc:
        _bolt_app_error = str(exc)
        raise RuntimeError(f"Slack app initialization failed: {_bolt_app_error}") from exc


def get_bolt_app_error() -> str | None:
    return _bolt_app_error
