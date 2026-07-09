"""add skills_text generated column and bm25 index to jobs

Revision ID: 6c509e73e48d
Revises: 56704b70cfc0
Create Date: 2026-07-05 21:47:23.413601

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c509e73e48d"
down_revision: str | Sequence[str] | None = "56704b70cfc0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pg_textsearch is optional — use a savepoint so a failure doesn't
    # poison the outer migration transaction.
    conn = op.get_bind()
    try:
        with conn.begin_nested():
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_textsearch"))
    except Exception:
        pass  # nosec: idempotent migration — extension may already exist

    op.execute(
        """
        CREATE OR REPLACE FUNCTION immutable_array_to_string(text[], text)
            RETURNS text
            LANGUAGE sql
            IMMUTABLE
            PARALLEL SAFE
        AS $$ SELECT array_to_string($1, $2); $$
        """
    )

    op.add_column(
        "jobs",
        sa.Column(
            "skills_text",
            sa.String(),
            sa.Computed(
                "immutable_array_to_string(required_skills, ' ')", persisted=True
            ),
            nullable=False,
        ),
    )

    try:
        with conn.begin_nested():
            op.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_skills_bm25
                    ON jobs USING bm25 (skills_text)
                    WITH (text_config = 'english')
                """
            )
    except Exception:
        # Fallback to GIN trigram index if BM25 extension is unavailable
        try:
            with conn.begin_nested():
                conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception:
            pass  # nosec: idempotent migration — index may already exist
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jobs_skills_trgm
                ON jobs USING GIN (skills_text gin_trgm_ops)
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jobs_skills_bm25")
    op.drop_column("jobs", "skills_text")
    op.execute("DROP FUNCTION IF EXISTS immutable_array_to_string(text[], text)")
