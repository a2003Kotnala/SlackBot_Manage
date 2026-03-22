from fastapi import APIRouter

from app.domain.schemas.followthru import (
    FollowThruCapabilitiesResponse,
    FollowThruChatRequest,
    FollowThruResponse,
    FollowThruVoiceCommandRequest,
)
from app.domain.services.followthru_service import (
    build_followthru_capabilities,
    handle_followthru_chat,
    handle_followthru_voice_command,
)

router = APIRouter(prefix="/api/v1/followthru", tags=["followthru"])


@router.get("/capabilities", response_model=FollowThruCapabilitiesResponse)
def followthru_capabilities() -> FollowThruCapabilitiesResponse:
    return build_followthru_capabilities()


@router.post("/chat", response_model=FollowThruResponse)
def followthru_chat(payload: FollowThruChatRequest) -> FollowThruResponse:
    return handle_followthru_chat(payload)


@router.post("/voice-command", response_model=FollowThruResponse)
def followthru_voice_command(
    payload: FollowThruVoiceCommandRequest,
) -> FollowThruResponse:
    return handle_followthru_voice_command(payload)
