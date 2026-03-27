from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.base import engine

router = APIRouter(tags=["health"])

@router.get("/")
def home():
    return {
        "status": "ok",
        "message": "Welcome to the FollowThru API"
        }

@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "database_target": "postgresql" if settings.is_postgresql else "sqlite",
        "bot": {
            "name": settings.app_name,
            "primary_slack_command": settings.primary_slack_command,
            "legacy_slack_command": settings.legacy_slack_command,
            "voice_transcript_commands_enabled": True,
        },
        "integrations": {
            "slack_configured": settings.slack_configured,
            "llm_provider": settings.llm_provider,
            "llm_configured": settings.llm_configured,
            "openai_configured": settings.openai_configured,
        },
    }


@router.get("/db-health")
def db_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "error", "database": "disconnected", "detail": str(exc)}
