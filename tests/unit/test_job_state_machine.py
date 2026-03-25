import pytest

from app.domain.schemas.ingestion import IngestionJobStatus
from app.domain.services.job_state_machine import validate_job_transition


def test_state_machine_allows_expected_transition():
    validate_job_transition(
        IngestionJobStatus.validated,
        IngestionJobStatus.queued,
    )


def test_state_machine_rejects_invalid_transition():
    with pytest.raises(ValueError):
        validate_job_transition(
            IngestionJobStatus.received,
            IngestionJobStatus.completed,
        )
