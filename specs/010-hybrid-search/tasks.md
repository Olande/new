---
description: "Task list for Hybrid Search — all tasks completed (migrated)"
---

# Tasks: Hybrid Search

**Status**: All tasks [x] completed (migrated from existing codebase)

## Phase 1: SQL Function

- [x] T001 Design and implement `hybrid_search_jobs()` PostgreSQL function with three CTEs (BM25, vector, RRF fusion)
- [x] T02 Add `skills_text` generated column to `jobs` table (concatenates `required_skills` for BM25 indexing)
- [x] T03 Create BM25 GIN index `idx_jobs_skills_bm25` on `skills_text`
- [x] T04 Apply embedding join via `entity_type = 'job'` filter on `embeddings` table

## Phase 2: Python Caller

- [x] T05 Create `search_jobs()` in `app/retrieval/hybrid_search.py` with embedding + SQL call
- [x] T06 Integrate with `get_embeddings_client()` for query embedding
- [x] T07 Return typed `JobSearchResult` list with RRF scores

## Phase 3: Evaluation & Tuning

- [x] T08 Build evaluation pipeline in `app/evaluation/search.py` to measure Recall@k
- [x] T09 Set up Optuna HPO (`app/evaluation/run_eval.py`) to tune weights + threshold
- [x] T10 Run hyperparameter optimization to find optimal (bm25_weight, vector_weight, threshold)
- [x] T11 Apply tuned parameters (bm25=0.2069, vector=0.7931, threshold=0.4513)

## Phase 4: Integration

- [x] T12 Wire hybrid search into `JobRepository.search_jobs()` → `JobService.search_jobs()`
- [x] T13 Wire into MCP `search_jobs_tool` for user-facing search

## Gaps Identified

| Gap | Type | Recommendation |
|-----|------|----------------|
| ⚠️ No standalone test for hybrid search | Test gap | Add `tests/test_hybrid_search.py` with mocked embeddings and known dataset |
| ⚠️ `cosine_distance_threshold` name is misleading | Clarity | The parameter is actually a cosine *distance* threshold (not similarity) — rename or document clearly |
| ℹ️ RRF constant `k=60` is hardcoded in SQL | Config | Consider making `k` a function parameter for tunability |
