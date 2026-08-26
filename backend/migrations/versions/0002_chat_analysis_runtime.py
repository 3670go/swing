"""Add canonical chat and analysis runtime tables.

Revision ID: 0002_chat_analysis_runtime
Revises: 0001_private_media_storage
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_chat_analysis_runtime"
down_revision: str | None = "0001_private_media_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store validated analysis results and canonical chat messages."""
    op.drop_constraint("ck_media_assets_kind", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_kind",
        "media_assets",
        "kind IN ('original_video', 'original_photo', 'frame', 'annotated_frame')",
    )

    op.create_table(
        "analysis_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "swing_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("swing_sessions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("media_kind", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("observation_json", postgresql.JSONB(), nullable=True),
        sa.Column("reply_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'limited', 'rejected', 'failed', 'deleted')",
            name="ck_analysis_runs_status",
        ),
        sa.CheckConstraint(
            "media_kind IN ('photo', 'video')",
            name="ck_analysis_runs_media_kind",
        ),
    )
    op.create_index("ix_analysis_runs_conversation_id", "analysis_runs", ["conversation_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])

    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_runs.id"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_chat_messages_role",
        ),
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])

    for table_name in ("analysis_runs", "chat_messages"):
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')

    op.execute(
        """
        UPDATE storage.buckets
        SET allowed_mime_types = ARRAY[
            'video/mp4', 'video/quicktime', 'video/webm',
            'image/jpeg', 'image/png', 'image/webp'
        ]
        WHERE id = 'swing-media'
        """
    )


def downgrade() -> None:
    """Remove chat runtime tables while preserving original media tables."""
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_analysis_runs_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_conversation_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")

    op.drop_constraint("ck_media_assets_kind", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_kind",
        "media_assets",
        "kind IN ('original_video', 'frame', 'annotated_frame')",
    )
    op.execute(
        """
        UPDATE storage.buckets
        SET allowed_mime_types = ARRAY['video/mp4', 'video/quicktime', 'video/webm']
        WHERE id = 'swing-media'
        """
    )
