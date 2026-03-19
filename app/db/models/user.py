import uuid

from sqlalchemy import Column, DateTime, String, Uuid

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    slack_user_id = Column(String, unique=True)
    name = Column(String)
    email = Column(String)
    created_at = Column(DateTime)
