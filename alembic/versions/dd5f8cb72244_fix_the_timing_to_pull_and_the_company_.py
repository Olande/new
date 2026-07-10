"""Fix the timing to pull and the company summary

Revision ID: dd5f8cb72244
Revises: baae3c78a42e
Create Date: 2026-07-09 16:01:57.142932

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd5f8cb72244"
down_revision: str | Sequence[str] | None = "baae3c78a42e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    try:
        with conn.begin_nested():
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_textsearch"))
    except Exception:  # nosec
        pass

    op.execute(
        """
        ALTER TABLE jobs ADD COLUMN IF NOT EXISTS skills_text VARCHAR GENERATED ALWAYS AS (
            immutable_array_to_string(required_skills, ' ')
        ) STORED;
        """
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
        try:
            with conn.begin_nested():
                conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception:  # nosec
            pass
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jobs_skills_trgm
                ON jobs USING GIN (skills_text gin_trgm_ops)
            """
        )

    op.execute(
        "DROP FUNCTION IF EXISTS hybrid_search_jobs(vector, text, integer, integer, double precision, double precision, double precision)"
    )
    op.execute("""
CREATE OR REPLACE FUNCTION hybrid_search_jobs(
    query_text TEXT,
    query_embedding VECTOR(1024),
    cosine_distance_threshold FLOAT DEFAULT 0.5,
    bm25_weight FLOAT DEFAULT 0.1,
    vector_weight FLOAT DEFAULT 0.9,
    result_limit INT DEFAULT 20
)
    RETURNS TABLE
            (
                id              UUID,
                dedup_hash      TEXT,
                title           TEXT,
                company_name    TEXT,
                domain_name     TEXT,
                role            TEXT,
                job_function    TEXT,
                seniority       TEXT[],
                employment_type TEXT,
                remote_type     TEXT,
                locations       TEXT[],
                countries       TEXT[],
                required_skills TEXT[],
                employee_count  TEXT,
                funding         TEXT,
                company_summary TEXT,
                status          TEXT,
                posted_at       TIMESTAMPTZ,
                last_seen_at    TIMESTAMPTZ,
                created_at      TIMESTAMPTZ,
                rrf_score       FLOAT
            )
    LANGUAGE sql
    STABLE
AS
$$
WITH bm25_results AS (SELECT j.id  AS job_id,
                             ROW_NUMBER() OVER (
                                 ORDER BY j.skills_text <@> to_bm25query(query_text, 'idx_jobs_skills_bm25') ASC
                                 ) AS rank
                      FROM jobs j
                      WHERE j.status = 'active'
                      ORDER BY j.skills_text <@> to_bm25query(query_text, 'idx_jobs_skills_bm25') ASC
                      LIMIT 20),
     vector_results AS (SELECT e.entity_id                                               AS job_id,
                               ROW_NUMBER() OVER (ORDER BY e.vector <=> query_embedding) AS rank
                        FROM embeddings e
                        WHERE e.entity_type = 'job'
                          AND (e.vector <=> query_embedding) < cosine_distance_threshold
                        ORDER BY e.vector <=> query_embedding
                        LIMIT 20),
     fused AS (SELECT COALESCE(b.job_id, v.job_id)                       AS job_id,
                      COALESCE(bm25_weight * (1.0 / (60 + b.rank)), 0) +
                      COALESCE(vector_weight * (1.0 / (60 + v.rank)), 0) AS rrf_score
               FROM bm25_results b
                        FULL OUTER JOIN vector_results v ON b.job_id = v.job_id)
SELECT j.id,
       j.dedup_hash,
       j.title,
       j.company_name,
       j.domain_name,
       j.role,
       j.job_function,
       j.seniority,
       j.employment_type,
       j.remote_type,
       j.locations,
       j.countries,
       j.required_skills,
       j.employee_count,
       j.funding,
       j.company_summary,
       j.status,
       j.posted_at,
       j.last_seen_at,
       j.created_at,
       f.rrf_score
FROM fused f
         JOIN jobs j ON j.id = f.job_id
WHERE j.status = 'active'
ORDER BY f.rrf_score DESC
LIMIT result_limit;
$$;
""")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP FUNCTION IF EXISTS hybrid_search_jobs(text, vector, double precision, double precision, double precision, integer)"
    )
    op.execute("""
CREATE OR REPLACE FUNCTION hybrid_search_jobs(
    query_embedding vector,
    query_text text,
    k integer,
    candidate_pool integer DEFAULT 200,
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
                         AND e.vector <=> query_embedding < 0.55
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
    op.execute("DROP INDEX IF EXISTS idx_jobs_skills_bm25")
    op.execute("DROP INDEX IF EXISTS idx_jobs_skills_trgm")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS skills_text")
