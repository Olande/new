---
description: "Task list for LLM Embeddings — all tasks completed (migrated)"
---

# Tasks: LLM Embeddings

**Status**: All tasks [x] completed (migrated from existing codebase)

## Phase 1: Embedding Client & Text Construction

- [x] T001 Create `get_embeddings_client()` factory for `GoogleGenerativeAIEmbeddings` (gemini-embedding-2, 1024d)
- [x] T02 Create `JobEmbeddingDocument` Pydantic model for structured embedding input
- [x] T03 Implement `build_job_embedding_text()`: serialize job fields into embedding input text
- [x] T04 Implement `compute_job_embedding_hash()`: SHA-256 of versioned text content

## Phase 2: Staleness Detection

- [x] T05 Implement `fetch_active_jobs()` with description eager loading
- [x] T06 Implement `fetch_existing_embeddings()` bulk query by entity_type='job'
- [x] T07 Implement `needs_embedding_update()`: hash mismatch OR expired valid_until
- [x] T08 Implement `collect_stale_jobs()`: identify jobs requiring new embeddings

## Phase 3: Batch Embedding & Retry

- [x] T09 Implement `embed_texts_in_batches()` with configurable batch size (10) and concurrency (3)
- [x] T10 Configure tenacity retry: 5 attempts, exponential jitter (1s-30s), on ResourceExhausted + ServiceUnavailable
- [x] T11 Use `asyncio.TaskGroup` for concurrent batch execution

## Phase 4: Storage & Refresh

- [x] T12 Implement `apply_embedding_update()`: INSERT or UPDATE Embedding row with vector + hash + model info
- [x] T13 Implement `refresh_stale_embeddings()`: orchestrate the full refresh pipeline
- [x] T14 Integrate refresh into JDL discovery cycle (`app/core/jdl/discovery.py` line 89-96)

## Phase 5: Integration

- [x] T15 Ensure `Embedding` model exists with `vector(1024)` column, entity_type enum, hash, valid_until
- [x] T16 Wire embedding refresh into `run_discovery()` post-ingestion

## Gaps Identified

| Gap | Type | Recommendation |
|-----|------|----------------|
| ❌ No embedding tests | Test gap | Add `tests/test_embeddings.py` with mock Gemini client — test hash detection, batch splitting, retry logic |
| ⚠️ `Embedding.entity_id` is a string — not FK-constrained | Data integrity | Consider adding FK constraint or at least validating entity_id format per EntityType |
| ℹ️ Only `job` entity type supported | Scope | Embeddings table supports `EntityType` enum but only 'job' is implemented — `user`, `memory` are unused |
