from __future__ import annotations

from fastapi import Request
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from slack_bolt.error import BoltError
from starlette.responses import Response

from app.config import settings

_bolt_app: App | None = None
_bolt_handler: SlackRequestHandler | None = None
_bolt_app_error: str | None = None


def get_bolt_app() -> App:
    global _bolt_app, _bolt_handler, _bolt_app_error

    if _bolt_app is not None:
        return _bolt_app

    if not settings.slack_configured:
        _bolt_app_error = "Slack credentials are not configured."
        raise RuntimeError(_bolt_app_error)

    try:
        _bolt_app = App(
            token=settings.slack_bot_token,
            signing_secret=settings.slack_signing_secret,
        )
        from app.slack.handlers.commands import register_handlers

        register_handlers(_bolt_app)
        _bolt_handler = SlackRequestHandler(_bolt_app)
        return _bolt_app
    except BoltError as exc:
        _bolt_app_error = str(exc)
        raise RuntimeError(
            f"Slack app initialization failed: {_bolt_app_error}"
        ) from exc


async def handle_slack_request(request: Request) -> Response:
    global _bolt_handler
    get_bolt_app()
    if _bolt_handler is None:
        raise RuntimeError("Slack request handler is unavailable.")
    return await _bolt_handler.handle(request)


def get_bolt_app_error() -> str | None:
    return _bolt_app_error