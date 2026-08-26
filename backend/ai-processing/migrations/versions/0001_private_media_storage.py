"""Create owner, swing session, and private media metadata.

Revision ID: 0001_private_media_storage
Revises:
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_private_media_storage"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIVATE_BUCKET = "swing-media"


def upgrade() -> None:
    """Create the minimum canonical tables and one private video bucket."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "owner_contexts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("anonymous_session_hash", sa.Text(), nullable=True, unique=True),
        sa.Column("external_provider", sa.Text(), nullable=True),
        sa.Column("external_subject", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("default_handedness", sa.String(length=16), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "external_provider",
            "external_subject",
            name="uq_owner_contexts_external_subject",
        ),
    )

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_context_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_contexts.id"),
            nullable=False,
        ),
        sa.Column("active_analysis_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shot_profile", sa.String(length=32), nullable=True),
        sa.Column("club", sa.String(length=64), nullable=True),
        sa.Column("analysis_goal", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_conversations_owner_context_id", "conversations", ["owner_context_id"])

    op.create_table(
        "swing_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_context_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_contexts.id"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("shot_profile", sa.String(length=32), nullable=False),
        sa.Column("club", sa.String(length=64), nullable=False),
        sa.Column("camera_view", sa.String(length=32), nullable=False),
        sa.Column("handedness", sa.String(length=16), nullable=False),
        sa.Column("user_question", sa.Text(), nullable=True),
        sa.Column("user_feel", sa.Text(), nullable=True),
        sa.Column("shot_result_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "comparison_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("swing_sessions.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "shot_profile IN ('full_swing', 'short_game')",
            name="ck_swing_sessions_shot_profile",
        ),
    )
    op.create_index("ix_swing_sessions_owner_context_id", "swing_sessions", ["owner_context_id"])
    op.create_index("ix_swing_sessions_conversation_id", "swing_sessions", ["conversation_id"])

    op.create_table(
        "media_assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("swing_sessions.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False, unique=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending_upload'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "kind IN ('original_video', 'frame', 'annotated_frame')",
            name="ck_media_assets_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending_upload', 'uploaded', 'failed', 'deleted')",
            name="ck_media_assets_status",
        ),
    )
    op.create_index("ix_media_assets_session_id", "media_assets", ["session_id"])
    op.create_index("ix_media_assets_status", "media_assets", ["status"])

    for table_name in ("owner_contexts", "conversations", "swing_sessions", "media_assets"):
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')

    op.execute(
        f"""
        INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
        VALUES (
            '{PRIVATE_BUCKET}',
            '{PRIVATE_BUCKET}',
            false,
            NULL,
            ARRAY['video/mp4', 'video/quicktime', 'video/webm']
        )
        ON CONFLICT (id) DO UPDATE SET
            public = false,
            allowed_mime_types = EXCLUDED.allowed_mime_types
        """
    )


def downgrade() -> None:
    """Reverse only when the private bucket contains no objects."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM storage.objects WHERE bucket_id = '{PRIVATE_BUCKET}' LIMIT 1
            ) THEN
                RAISE EXCEPTION
                    'Refusing downgrade: private bucket {PRIVATE_BUCKET} still contains objects';
            END IF;
            DELETE FROM storage.buckets WHERE id = '{PRIVATE_BUCKET}';
        END
        $$
        """
    )
    op.drop_index("ix_media_assets_status", table_name="media_assets")
    op.drop_index("ix_media_assets_session_id", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_swing_sessions_conversation_id", table_name="swing_sessions")
    op.drop_index("ix_swing_sessions_owner_context_id", table_name="swing_sessions")
    op.drop_table("swing_sessions")
    op.drop_index("ix_conversations_owner_context_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("owner_contexts")
