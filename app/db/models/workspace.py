import uuid

from sqlalchemy import Column, DateTime, String, Uuid

from app.db.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    slack_team_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
