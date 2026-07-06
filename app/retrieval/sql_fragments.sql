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
                                   ORDER BY j.skills_text <@> to_bm25query(query_text, 'idx_jobs_skills_bm25')
                                   ) AS rank
                        FROM jobs j
                        WHERE query_text <> ''
                          AND j.status = 'active'
                        LIMIT candidate_pool),
     trigram_search AS (SELECT j.id                                                              AS job_id,
                               ROW_NUMBER() OVER (ORDER BY similarity(j.title, query_text) DESC) AS rank
                        FROM jobs j
                        WHERE j.title % query_text
                          AND j.status = 'active'
                        LIMIT candidate_pool),
     rrf AS (SELECT COALESCE(v.job_id, l.job_id, t.job_id)                        AS job_id,
                    (semantic_weight * COALESCE(1.0 / (60.0 + v.rank), 0.0))
                        + (lexical_weight * COALESCE(1.0 / (60.0 + l.rank), 0.0))
                        + (trigram_weight * COALESCE(1.0 / (60.0 + t.rank), 0.0)) AS rrf_score
             FROM vector_search v
                      FULL OUTER JOIN lexical_search l ON v.job_id = l.job_id
                      FULL OUTER JOIN trigram_search t ON COALESCE(v.job_id, l.job_id) = t.job_id)
SELECT r.job_id, r.rrf_score
FROM rrf r
         JOIN jobs j ON r.job_id = j.id
WHERE j.status = 'active'
ORDER BY r.rrf_score DESC
LIMIT k;
$$;