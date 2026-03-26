import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text, Uuid

from app.db.base import Base


class ExtractionResultRecord(Base):
    __tablename__ = "extraction_results"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("ingestion_jobs.id"), nullable=False)
    draft_id = Column(Uuid, ForeignKey("drafts.id"), nullable=True)
    confidence = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    structured_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
