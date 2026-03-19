from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

engine = create_engine(
    settings.resolved_database_url,
    echo=True if settings.app_env == "development" else False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if settings.is_sqlite else {},
)
Base = declarative_base()
