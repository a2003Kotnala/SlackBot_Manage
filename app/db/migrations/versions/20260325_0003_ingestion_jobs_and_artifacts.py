"""ingestion jobs, provider access, and artifact persistence

Revision ID: 20260325_0003
Revises: 20260323_0002
Create Date: 2026-03-25 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260325_0003"
down_revision = "20260323_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    source_type = sa.Enum(
        "transcript_text",
        "transcript_file",
        "recording_link",
        "media_file",
        "slack_huddle_file",
        "unsupported",
        name="ingestionsourcetype",
        native_enum=False,
    )
    provider_type = sa.Enum(
        "none",
        "zoom",
        "generic",
        name="providertype",
        native_enum=False,
    )
    job_status = sa.Enum(
        "received",
        "classified",
        "validated",
        "queued",
        "fetching_source",
        "fetched",
        "normalizing_media",
        "transcribing",
        "cleaning_transcript",
        "extracting_intelligence",
        "rendering_canvas",
        "completed",
        "failed",
        "retrying",
        "needs_permission",
        "unsupported_source",
        name="ingestionjobstatus",
        native_enum=False,
    )
    followthru_mode = sa.Enum(
        "help",
        "chat",
        "preview",
        "draft",
        "publish",
        name="followthrumode",
        native_enum=False,
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slack_team_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slack_team_id"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("provider_type", provider_type, nullable=False),
        sa.Column("requested_mode", followthru_mode, nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_reference", sa.String(), nullable=True),
        sa.Column("slack_channel_id", sa.String(), nullable=True),
        sa.Column("slack_thread_ts", sa.String(), nullable=True),
        sa.Column("slack_message_ts", sa.String(), nullable=True),
        sa.Column("slack_status_ts", sa.String(), nullable=True),
        sa.Column("status", job_status, nullable=False),
        sa.Column("progress_state", sa.String(), nullable=False),
        sa.Column("current_step", sa.String(), nullable=False),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )

    op.create_table(
        "source_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("storage_path", sa.String(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "normalized_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "transcript_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("provenance", sa.String(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["source_artifacts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "extraction_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("structured_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "canvas_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("slack_canvas_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "retry_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "provider_access_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", sa.String(), nullable=False),
        sa.Column("normalized_url", sa.String(), nullable=False),
        sa.Column("external_reference", sa.String(), nullable=True),
        sa.Column("access_status", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_ingestion_jobs_workspace_status",
        "ingestion_jobs",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_ingestion_jobs_channel_message",
        "ingestion_jobs",
        ["slack_channel_id", "slack_message_ts"],
    )
    op.create_index("ix_source_artifacts_job_id", "source_artifacts", ["job_id"])
    op.create_index(
        "ix_normalized_artifacts_job_id",
        "normalized_artifacts",
        ["job_id"],
    )
    op.create_index(
        "ix_transcript_artifacts_job_id",
        "transcript_artifacts",
        ["job_id"],
    )
    op.create_index("ix_extraction_results_job_id", "extraction_results", ["job_id"])
    op.create_index("ix_canvas_versions_job_id", "canvas_versions", ["job_id"])
    op.create_index("ix_audit_logs_job_id", "audit_logs", ["job_id"])
    op.create_index("ix_retry_records_job_id", "retry_records", ["job_id"])
    op.create_index(
        "ix_provider_access_records_job_id",
        "provider_access_records",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_access_records_job_id", table_name="provider_access_records"
    )
    op.drop_index("ix_retry_records_job_id", table_name="retry_records")
    op.drop_index("ix_audit_logs_job_id", table_name="audit_logs")
    op.drop_index("ix_canvas_versions_job_id", table_name="canvas_versions")
    op.drop_index("ix_extraction_results_job_id", table_name="extraction_results")
    op.drop_index("ix_transcript_artifacts_job_id", table_name="transcript_artifacts")
    op.drop_index("ix_normalized_artifacts_job_id", table_name="normalized_artifacts")
    op.drop_index("ix_source_artifacts_job_id", table_name="source_artifacts")
    op.drop_index("ix_ingestion_jobs_channel_message", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_workspace_status", table_name="ingestion_jobs")

    op.drop_table("provider_access_records")
    op.drop_table("retry_records")
    op.drop_table("audit_logs")
    op.drop_table("canvas_versions")
    op.drop_table("extraction_results")
    op.drop_table("transcript_artifacts")
    op.drop_table("normalized_artifacts")
    op.drop_table("source_artifacts")
    op.drop_table("ingestion_jobs")
    op.drop_table("workspaces")
