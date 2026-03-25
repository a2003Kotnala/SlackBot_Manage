import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text, Uuid

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("ingestion_jobs.id"), nullable=False)
    event_type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    payload_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
