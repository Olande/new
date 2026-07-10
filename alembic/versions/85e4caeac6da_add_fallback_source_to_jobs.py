"""Add fallback_source column to jobs table

Revision ID: 85e4caeac6da
Revises: dd5f8cb72244
Create Date: 2026-07-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "85e4caeac6da"
down_revision: str | Sequence[str] | None = "dd5f8cb72244"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("jobs", sa.Column("fallback_source", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("jobs", "fallback_source")
