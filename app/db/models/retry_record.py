import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Uuid

from app.db.base import Base


class RetryRecord(Base):
    __tablename__ = "retry_records"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("ingestion_jobs.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    error_type = Column(String, nullable=False)
    failure_reason = Column(Text, nullable=False)
    next_retry_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
