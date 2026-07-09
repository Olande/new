"""merge heads

Revision ID: baae3c78a42e
Revises: a1b2c3d4e5f6, ce5bff24a49c
Create Date: 2026-07-09 12:10:52.372401

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "baae3c78a42e"
down_revision: str | Sequence[str] | None = ("a1b2c3d4e5f6", "ce5bff24a49c")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
