# Implementation Plan: Hybrid Search

**Branch**: Multiple (iterative) | **Status**: Migrated | **Spec**: `specs/010-hybrid-search/spec.md`

## Summary

Implement hybrid search combining BM25 full-text search (on `skills_text` generated column) with pgvector cosine similarity (on job embeddings), fused via Reciprocal Rank Fusion (RRF). Implemented as a single PostgreSQL function `hybrid_search_jobs()` called from `app/retrieval/hybrid_search.py`.

## Technical Context

**Language/Version**: Python 3.13+ (caller) + PostgreSQL PL/pgSQL (function)
**Primary Dependencies**: `pgvector` (cosine distance), `pg_bm25` or equivalent (BM25), SQLAlchemy `text()` for raw SQL execution
**Storage**: PostgreSQL — `jobs.skills_text` (generated BM25 column), `embeddings.vector` (pgvector)
**Testing**: ❌ No dedicated test file (`test_evaluation.py` has related eval tests)

## Search Architecture

```
User Query
    │
    ▼
app/retrieval/hybrid_search.py
    │
    ├─ get_embeddings_client() → aembed_query(query) → query_embedding (vector)
    │
    └─ CALL hybrid_search_jobs(query_text, query_embedding, threshold, bm25_weight, vector_weight, limit)
            │
            ├─ CTE 1: BM25 results  ← skills_text <@> to_bm25query()
            ├─ CTE 2: Vector results ← Embedding.vector <=> query_embedding
            └─ CTE 3: RRF fusion      ← FULL OUTER JOIN + RRF scoring
                    │
                    ▼
            RETURN jobs JOIN fused
                    │
                    ▼
            ORDER BY rrf_score DESC LIMIT result_limit
```

## Key Design Decisions

1. **RRF fusion**: `COALESCE(bm25_weight * (1/(60+b.rank)), 0) + COALESCE(vector_weight * (1/(60+v.rank)), 0)` — handles cases where a job is found by only one method via FULL OUTER JOIN
2. **Single SQL function**: All logic in one PostgreSQL function for performance (no client-side fusion)
3. **Separate embedding call**: Query is embedded in Python (not SQL) to support interchangeable embedding models
4. **Configurable weights**: Weights optimized via evaluation pipeline in `app/evaluation/` using Optuna HPO

## Parameter Tuning History

| Parameter | Value | Source |
|-----------|-------|--------|
| `cosine_distance_threshold` | 0.4513 | Optuna HPO |
| `bm25_weight` | 0.2069 | Optuna HPO |
| `vector_weight` | 0.7931 | Optuna HPO |
| RRF constant `k` | 60 | Heuristic |
| `result_limit` | 20 | Default |

## Related Migrations

| Migration | Change |
|-----------|--------|
| `6c50...` | Add `skills_text` generated column + BM25 index on jobs |
| `2e8e...` | Create/update hybrid search function |
| `ce5b...` | Update hybrid search params |
| `f3e2...` | Update hybrid search weights |
| `6952...` | Add semantic distance threshold (later removed in `a1b2...`) |
