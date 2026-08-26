"""Add deterministic conversation policy metadata.

Revision ID: 0003_chat_interaction_metadata
Revises: 0002_chat_analysis_runtime
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_chat_interaction_metadata"
down_revision: str | None = "0002_chat_analysis_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store non-user-facing cadence metadata beside assistant messages."""
    op.add_column(
        "chat_messages",
        sa.Column("interaction_meta_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Remove conversation policy metadata without deleting chat content."""
    op.drop_column("chat_messages", "interaction_meta_json")
