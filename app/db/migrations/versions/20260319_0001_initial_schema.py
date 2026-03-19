"""initial schema

Revision ID: 20260319_0001
Revises:
Create Date: 2026-03-19 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260319_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    source_type = sa.Enum(
        "huddle_notes",
        "text",
        "csv",
        "voice",
        "thread",
        name="sourcetype",
        native_enum=False,
    )
    draft_status = sa.Enum(
        "draft", "shared", "archived", name="draftstatus", native_enum=False
    )
    item_type = sa.Enum(
        "summary",
        "decision",
        "action_item",
        "owner",
        "due_date",
        "question",
        "blocker",
        name="itemtype",
        native_enum=False,
    )
    confidence = sa.Enum(
        "high",
        "medium",
        "low",
        "needs_review",
        name="confidence",
        native_enum=False,
    )
    share_type = sa.Enum("channel", "user", name="sharetype", native_enum=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slack_user_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slack_user_id"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", source_type, nullable=True),
        sa.Column("slack_channel_id", sa.String(), nullable=True),
        sa.Column("slack_thread_ts", sa.String(), nullable=True),
        sa.Column("slack_canvas_id", sa.String(), nullable=True),
        sa.Column("raw_content_reference", sa.String(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("slack_canvas_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("status", draft_status, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "extracted_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=True),
        sa.Column("item_type", item_type, nullable=True),
        sa.Column("content", sa.String(), nullable=True),
        sa.Column("confidence", confidence, nullable=True),
        sa.Column("assignee", sa.String(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "shares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=True),
        sa.Column("share_type", share_type, nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("shared_by", sa.Uuid(), nullable=True),
        sa.Column("shared_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"]),
        sa.ForeignKeyConstraint(["shared_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("shares")
    op.drop_table("extracted_items")
    op.drop_table("drafts")
    op.drop_table("sources")
    op.drop_table("users")
