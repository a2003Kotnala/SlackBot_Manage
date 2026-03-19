from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.base import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
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
