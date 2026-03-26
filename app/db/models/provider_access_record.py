import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Uuid

from app.db.base import Base


class ProviderAccessRecord(Base):
    __tablename__ = "provider_access_records"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("ingestion_jobs.id"), nullable=False)
    provider_type = Column(String, nullable=False)
    normalized_url = Column(String, nullable=False)
    external_reference = Column(String, nullable=True)
    access_status = Column(String, nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
