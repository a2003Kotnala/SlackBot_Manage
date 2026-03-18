from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from app.config import settings

engine = create_engine(
    settings.resolved_database_url,
    echo=True if settings.app_env == "development" else False,
    pool_pre_ping=True,
)
Base = declarative_base()
