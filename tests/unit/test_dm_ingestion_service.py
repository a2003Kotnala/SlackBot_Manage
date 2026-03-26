from types import SimpleNamespace
from uuid import uuid4

from app.slack.services.dm_ingestion_service import handle_dm_ingestion_event


def test_dm_ingestion_service_enqueues_new_job(monkeypatch):
    prepared: list[str] = []
    enqueued: list[str] = []
    recorded: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.slack.services.dm_ingestion_service.create_or_get_slack_ingestion_job",
        lambda **kwargs: SimpleNamespace(
            created=True,
            job=SimpleNamespace(id=uuid4()),
            classification=SimpleNamespace(requested_mode="publish"),
        ),
    )
    monkeypatch.setattr(
        "app.slack.services.dm_ingestion_service.prepare_job_for_enqueue",
        lambda job_id: prepared.append(str(job_id)),
    )
    monkeypatch.setattr(
        "app.slack.services.dm_ingestion_service.record_status_message",
        lambda job_id, message_ts: recorded.append((str(job_id), message_ts)),
    )
    monkeypatch.setattr(
        "app.slack.services.dm_ingestion_service.job_queue.enqueue",
        lambda job_id: enqueued.append(str(job_id)),
    )

    messages: list[str] = []
    handled = handle_dm_ingestion_event(
        event={
            "channel_type": "im",
            "team": "T123",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000200",
            "text": "Decision: Ship the pilot.",
        },
        say=lambda text: messages.append(text)
        or {"channel": "D123", "ts": "1710000000.000201"},
    )

    assert handled is True
    assert "Processing your meeting notes" in messages[0]
    assert prepared
    assert enqueued
    assert recorded[0][1] == "1710000000.000201"


def test_dm_ingestion_service_skips_duplicate_job(monkeypatch):
    monkeypatch.setattr(
        "app.slack.services.dm_ingestion_service.create_or_get_slack_ingestion_job",
        lambda **kwargs: SimpleNamespace(
            created=False,
            job=SimpleNamespace(id=uuid4()),
            classification=SimpleNamespace(requested_mode="publish"),
        ),
    )
    monkeypatch.setattr(
        "app.slack.services.dm_ingestion_service.prepare_job_for_enqueue",
        lambda job_id: (_ for _ in ()).throw(
            AssertionError("duplicate jobs must not be re-queued")
        ),
    )

    messages: list[str] = []
    handled = handle_dm_ingestion_event(
        event={
            "channel_type": "im",
            "team": "T123",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000200",
            "text": "Decision: Ship the pilot.",
        },
        say=lambda text: messages.append(text),
    )

    assert handled is True
    assert messages == []


def test_dm_ingestion_service_stop_requests_job_cancellation(monkeypatch):
    monkeypatch.setattr(
        "app.slack.services.dm_ingestion_service.request_job_stop",
        lambda _channel_id: SimpleNamespace(stopped=True, active=True),
    )

    messages: list[str] = []
    handled = handle_dm_ingestion_event(
        event={
            "channel_type": "im",
            "team": "T123",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000200",
            "text": "stop",
        },
        say=lambda text: messages.append(text),
    )

    assert handled is True
    assert messages == [
        "Stop requested. FollowThru will halt the current meeting job shortly."
    ]
