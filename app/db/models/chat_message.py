import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Text, Uuid

from app.db.base import Base


class ChatRole(enum.Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id = Column(Uuid, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(Enum(ChatRole, native_enum=False), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
