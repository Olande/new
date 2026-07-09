WITH bm25_results AS (SELECT j.id  AS job_id,
                             ROW_NUMBER() OVER (
                                 ORDER BY j.search_text <@> to_bm25query(:query_text, 'idx_jobs_search_bm25') ASC
                                 ) AS rank
                      FROM jobs j
                      WHERE j.status = 'active'
                      ORDER BY j.search_text <@> to_bm25query(:query_text, 'idx_jobs_search_bm25') ASC
                      LIMIT 20),
     vector_results AS (SELECT e.entity_id                                                AS job_id,
                               ROW_NUMBER() OVER (ORDER BY e.vector <=> :query_embedding) AS rank
                        FROM embedding e
                        WHERE e.entity_type = 'job'
                          AND (e.vector <=> :query_embedding) < :cosine_distance_threshold
                        ORDER BY e.vector <=> :query_embedding
                        LIMIT 20),
     fused AS (SELECT COALESCE(b.job_id, v.job_id)                        AS job_id,
                      COALESCE(:bm25_weight * (1.0 / (60 + b.rank)), 0) +
                      COALESCE(:vector_weight * (1.0 / (60 + v.rank)), 0) AS rrf_score
               FROM bm25_results b
                        FULL OUTER JOIN vector_results v ON b.job_id = v.job_id)
SELECT j.*, f.rrf_score
FROM fused f
         JOIN jobs j ON j.id = f.job_id
WHERE j.status = 'active'
ORDER BY f.rrf_score DESC
LIMIT :result_limit;
