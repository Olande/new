"""update_hybrid_search_function

Revision ID: 2e8e858a0038
Revises: 6413a88998d7
Create Date: 2026-07-08 17:40:58.396140

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e8e858a0038"
down_revision: str | Sequence[str] | None = "6413a88998d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
CREATE OR REPLACE FUNCTION hybrid_search_jobs(
    query_embedding vector,
    query_text text,
    k integer,
    candidate_pool integer DEFAULT 40,
    semantic_weight double precision DEFAULT 0.5,
    lexical_weight double precision DEFAULT 0.4,
    trigram_weight double precision DEFAULT 0.1
)
    RETURNS TABLE
            (
                job_id    uuid,
                rrf_score double precision
            )
    LANGUAGE sql
    STABLE
AS
$$
WITH vector_search AS (SELECT e.entity_id                                               AS job_id,
                              ROW_NUMBER() OVER (ORDER BY e.vector <=> query_embedding) AS rank
                       FROM embeddings e
                                JOIN jobs j ON e.entity_id = j.id
                       WHERE e.entity_type = 'job'
                         AND j.status = 'active'
                       LIMIT candidate_pool),
     lexical_search AS (SELECT j.id  AS job_id,
                               ROW_NUMBER() OVER (
                                   ORDER BY ts_rank(to_tsvector('english', array_to_string(j.required_skills, ' ')), plainto_tsquery('english', query_text)) DESC
                                   ) AS rank
                        FROM jobs j
                        WHERE query_text <> ''
                          AND j.status = 'active'
                          AND to_tsvector('english', array_to_string(j.required_skills, ' ')) @@ plainto_tsquery('english', query_text)
                        LIMIT candidate_pool),
     trigram_search AS (SELECT j.id                                                              AS job_id,
                               ROW_NUMBER() OVER (ORDER BY similarity(j.title, query_text) DESC) AS rank
                        FROM jobs j
                        WHERE j.title % query_text
                          AND j.status = 'active'
                        LIMIT candidate_pool),
     combined_scores AS (
         SELECT job_id, (semantic_weight * COALESCE(1.0 / (60.0 + rank), 0.0)) as score FROM vector_search
         UNION ALL
         SELECT job_id, (lexical_weight * COALESCE(1.0 / (60.0 + rank), 0.0)) as score FROM lexical_search
         UNION ALL
         SELECT job_id, (trigram_weight * COALESCE(1.0 / (60.0 + rank), 0.0)) as score FROM trigram_search
     ),
     rrf AS (
         SELECT job_id, SUM(score) AS rrf_score
         FROM combined_scores
         GROUP BY job_id
     )
SELECT r.job_id, r.rrf_score
FROM rrf r
         JOIN jobs j ON r.job_id = j.id
WHERE j.status = 'active'
ORDER BY r.rrf_score DESC
LIMIT k;
$$;
""")


def downgrade() -> None:
    """Downgrade schema."""
    pass
