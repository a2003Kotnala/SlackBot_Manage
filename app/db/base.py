from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

engine_kwargs = {
    "echo": settings.app_env == "development",
    "pool_pre_ping": True,
    "connect_args": {"check_same_thread": False} if settings.is_sqlite else {},
}
if settings.is_postgresql:
    engine_kwargs["pool_size"] = settings.database_pool_size
    engine_kwargs["max_overflow"] = settings.database_max_overflow

engine = create_engine(settings.resolved_database_url, **engine_kwargs)
Base = declarative_base()
