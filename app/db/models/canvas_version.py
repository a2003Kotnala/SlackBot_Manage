import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Uuid

from app.db.base import Base


class CanvasVersion(Base):
    __tablename__ = "canvas_versions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("ingestion_jobs.id"), nullable=False)
    draft_id = Column(Uuid, ForeignKey("drafts.id"), nullable=True)
    version_number = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=False)
    body_markdown = Column(Text, nullable=False)
    slack_canvas_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
