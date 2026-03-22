"""followthru chat persistence and operational indexes

Revision ID: 20260323_0002
Revises: 20260319_0001
Create Date: 2026-03-23 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260323_0002"
down_revision = "20260319_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    chat_role = sa.Enum(
        "system",
        "user",
        "assistant",
        name="chatrole",
        native_enum=False,
    )

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bot_name", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("slack_channel_id", sa.String(), nullable=True),
        sa.Column("slack_thread_ts", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("role", chat_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_sources_created_at", "sources", ["created_at"])
    op.create_index(
        "ix_sources_channel_created_at", "sources", ["slack_channel_id", "created_at"]
    )
    op.create_index("ix_drafts_source_id", "drafts", ["source_id"])
    op.create_index(
        "ix_drafts_owner_created_at", "drafts", ["owner_user_id", "created_at"]
    )
    op.create_index("ix_extracted_items_draft_id", "extracted_items", ["draft_id"])
    op.create_index("ix_shares_draft_id", "shares", ["draft_id"])
    op.create_index(
        "ix_chat_sessions_user_updated_at", "chat_sessions", ["user_id", "updated_at"]
    )
    op.create_index(
        "ix_chat_sessions_channel_thread",
        "chat_sessions",
        ["slack_channel_id", "slack_thread_ts"],
    )
    op.create_index(
        "ix_chat_messages_session_created_at",
        "chat_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_sessions_channel_thread", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_updated_at", table_name="chat_sessions")
    op.drop_index("ix_shares_draft_id", table_name="shares")
    op.drop_index("ix_extracted_items_draft_id", table_name="extracted_items")
    op.drop_index("ix_drafts_owner_created_at", table_name="drafts")
    op.drop_index("ix_drafts_source_id", table_name="drafts")
    op.drop_index("ix_sources_channel_created_at", table_name="sources")
    op.drop_index("ix_sources_created_at", table_name="sources")

    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
