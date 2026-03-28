import enum

from pydantic import BaseModel, Field

from app.domain.schemas.extraction import ExtractionResult

FOLLOWTHRU_MAX_INPUT_LENGTH = 100000


class FollowThruMode(str, enum.Enum):
    help = "help"
    chat = "chat"
    preview = "preview"
    draft = "draft"
    publish = "publish"


class FollowThruChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=FOLLOWTHRU_MAX_INPUT_LENGTH,
        description="User message or instruction for FollowThru.",
    )
    session_id: str | None = None
    user_id: str = "api-user"
    channel_id: str | None = None
    thread_ts: str | None = None


class FollowThruVoiceCommandRequest(BaseModel):
    transcript: str = Field(
        min_length=1,
        max_length=FOLLOWTHRU_MAX_INPUT_LENGTH,
        description="Speech-to-text transcript for a FollowThru voice command.",
    )
    session_id: str | None = None
    user_id: str = "voice-user"
    channel_id: str | None = None
    thread_ts: str | None = None


class FollowThruResponse(BaseModel):
    bot_name: str
    session_id: str
    mode: FollowThruMode
    reply: str
    source_id: str | None = None
    draft_id: str | None = None
    draft_title: str | None = None
    slack_canvas_id: str | None = None
    draft_canvas_markdown: str | None = None
    extraction: ExtractionResult | None = None
    normalized_input: str | None = None


class FollowThruCapabilitiesResponse(BaseModel):
    bot_name: str
    primary_slack_command: str
    legacy_slack_command: str
    supports_chat: bool
    supports_voice_transcript_commands: bool
    supports_slack_canvas_publish: bool
    supports_latest_huddle_resolution: bool
    supported_modes: list[FollowThruMode]
    quickstart_examples: list[str]
