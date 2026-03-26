import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text, Uuid

from app.db.base import Base


class TranscriptArtifact(Base):
    __tablename__ = "transcript_artifacts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("ingestion_jobs.id"), nullable=False)
    source_artifact_id = Column(Uuid, ForeignKey("source_artifacts.id"), nullable=True)
    source_kind = Column(String, nullable=False)
    provenance = Column(String, nullable=False)
    transcript_text = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
