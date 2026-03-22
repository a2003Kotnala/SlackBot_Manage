import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid

from app.db.base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    bot_name = Column(String, nullable=False)
    user_id = Column(Uuid, ForeignKey("users.id"))
    slack_channel_id = Column(String)
    slack_thread_ts = Column(String)
    title = Column(String)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
