from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app.domain.services.draft_service import (
    _resolve_owner_user_id,
    build_canvas_title_for_channel,
)


def test_resolve_owner_user_id_falls_back_to_source_creator_for_slack_ids():
    created_by = uuid4()
    source = SimpleNamespace(created_by=created_by)

    resolved = _resolve_owner_user_id("demo-user", source)

    assert resolved == created_by


def test_resolve_owner_user_id_accepts_uuid_strings():
    created_by = uuid4()
    owner_user_id = uuid4()
    source = SimpleNamespace(created_by=created_by)

    resolved = _resolve_owner_user_id(str(owner_user_id), source)

    assert resolved == owner_user_id


def test_build_canvas_title_for_dm_channel_is_compact():
    title = build_canvas_title_for_channel(
        "FollowThru Launch Readiness Review",
        "D123",
        datetime(2026, 3, 23, 14, 49),
    )

    assert title == "FollowThru Launch Readiness | 23 Mar 02:49 PM"


def test_build_canvas_title_for_channel_keeps_existing_prefix():
    title = build_canvas_title_for_channel(
        "FollowThru Launch Readiness Review",
        "C123",
        datetime(2026, 3, 23, 14, 49),
    )

    assert title == "Action Canvas - FollowThru Launch Readiness Review"
