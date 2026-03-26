import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text, Uuid

from app.db.base import Base


class NormalizedArtifact(Base):
    __tablename__ = "normalized_artifacts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("ingestion_jobs.id"), nullable=False)
    artifact_type = Column(String, nullable=False)
    storage_path = Column(String, nullable=True)
    text_content = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
