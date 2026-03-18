from fastapi import APIRouter
from sqlalchemy import text

from app.db.base import engine

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/db-health")
def db_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "error", "database": "disconnected", "detail": str(exc)}
