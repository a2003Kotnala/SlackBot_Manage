import enum
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.schemas.followthru import FollowThruMode


class IngestionSourceType(str, enum.Enum):
    transcript_text = "transcript_text"
    transcript_file = "transcript_file"
    recording_link = "recording_link"
    media_file = "media_file"
    slack_huddle_file = "slack_huddle_file"
    unsupported = "unsupported"


class ProviderType(str, enum.Enum):
    none = "none"
    zoom = "zoom"
    generic = "generic"


class IngestionJobStatus(str, enum.Enum):
    received = "received"
    classified = "classified"
    validated = "validated"
    queued = "queued"
    fetching_source = "fetching_source"
    fetched = "fetched"
    normalizing_media = "normalizing_media"
    transcribing = "transcribing"
    cleaning_transcript = "cleaning_transcript"
    extracting_intelligence = "extracting_intelligence"
    rendering_canvas = "rendering_canvas"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"
    needs_permission = "needs_permission"
    unsupported_source = "unsupported_source"


class ArtifactKind(str, enum.Enum):
    slack_message = "slack_message"
    transcript_text = "transcript_text"
    transcript_file = "transcript_file"
    recording_link = "recording_link"
    media_file = "media_file"
    normalized_audio = "normalized_audio"
    cleaned_transcript = "cleaned_transcript"
    extraction = "extraction"
    canvas = "canvas"


class SlackFileReference(BaseModel):
    id: str | None = None
    name: str = "uploaded-file"
    mimetype: str | None = None
    filetype: str | None = None
    url_private_download: str | None = None
    url_private: str | None = None
    preview: str | None = None
    size: int | None = None


class InputClassification(BaseModel):
    requested_mode: FollowThruMode = FollowThruMode.publish
    source_type: IngestionSourceType
    provider_type: ProviderType = ProviderType.none
    transcript_text: str | None = None
    recording_url: str | None = None
    media_filename: str | None = None
    message_text: str = ""
    slack_files: list[SlackFileReference] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


class ProviderReference(BaseModel):
    provider_type: ProviderType
    original_url: str
    normalized_url: str
    external_id: str | None = None


class TranscriptSegment(BaseModel):
    text: str
    speaker: str | None = None
    started_at: float | None = None
    ended_at: float | None = None


class TranscriptDocument(BaseModel):
    text: str
    source_kind: str
    provenance: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ProviderMetadata(BaseModel):
    title: str | None = None
    final_url: str
    accessible: bool
    metadata: dict = Field(default_factory=dict)


class ProviderFetchResult(BaseModel):
    metadata: ProviderMetadata
    transcript: TranscriptDocument | None = None
    media_download_url: str | None = None
    media_filename: str | None = None
    media_mimetype: str | None = None


class JobProgressUpdate(BaseModel):
    status: IngestionJobStatus
    step: str
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
