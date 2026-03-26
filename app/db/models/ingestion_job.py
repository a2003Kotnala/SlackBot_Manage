import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid

from app.db.base import Base
from app.domain.schemas.followthru import FollowThruMode
from app.domain.schemas.ingestion import (
    IngestionJobStatus,
    IngestionSourceType,
    ProviderType,
)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id = Column(Uuid, ForeignKey("workspaces.id"), nullable=False)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=True)
    source_type = Column(Enum(IngestionSourceType), nullable=False)
    provider_type = Column(Enum(ProviderType), nullable=False)
    requested_mode = Column(Enum(FollowThruMode), nullable=False)
    source_url = Column(String, nullable=True)
    source_reference = Column(String, nullable=True)
    slack_channel_id = Column(String, nullable=True)
    slack_thread_ts = Column(String, nullable=True)
    slack_message_ts = Column(String, nullable=True)
    slack_status_ts = Column(String, nullable=True)
    status = Column(Enum(IngestionJobStatus), nullable=False)
    progress_state = Column(String, nullable=False)
    current_step = Column(String, nullable=False)
    retries = Column(Integer, nullable=False, default=0)
    failure_reason = Column(Text, nullable=True)
    idempotency_key = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False)
