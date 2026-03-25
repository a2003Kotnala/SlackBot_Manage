import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, Uuid

from app.db.base import Base


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("ingestion_jobs.id"), nullable=False)
    artifact_type = Column(String, nullable=False)
    external_id = Column(String, nullable=True)
    filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    storage_path = Column(String, nullable=True)
    text_content = Column(Text, nullable=True)
    byte_size = Column(Integer, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
