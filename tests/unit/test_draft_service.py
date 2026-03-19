from types import SimpleNamespace
from uuid import uuid4

from app.domain.services.draft_service import _resolve_owner_user_id


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
