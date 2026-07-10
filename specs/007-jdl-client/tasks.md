---
description: "Task list for JDL Client feature — all tasks completed (migrated)"
---

# Tasks: JDL Client (Job Data Lake Integration)

**Status**: All tasks [x] completed (migrated from existing codebase)

## Phase 1: API Client & Schemas

- [x] T001 Create Pydantic schemas (`app/core/jdl/schemas.py`): `JobSearchCriteria`, `JobBase`, `JobCreate`, `JobRead`, `JobSourceCreate`, `JobEmbeddingDocument`
- [x] T02 Create `JobDataLakeClient` (`app/core/jdl/client.py`) with async HTTP client, rate limiting (30 req/min), retry transport (3 attempts, 5xx)
- [x] T03 Implement search params builder `build_search_params()` with query composition

## Phase 2: Normalization & Dedup

- [x] T04 Implement `RawJobInput` Pydantic model with multi-alias field parsing (date formats, location extraction)
- [x] T05 Implement `normalize_job()`: whitespace collape, skill dedup, SHA-256 dedup hash computation
- [x] T06 Implement `compute_dedup_hash(company, title, skills)` as deterministic SHA-256

## Phase 3: Database Layer

- [x] T07 Create `Job`, `JobSource`, `JobDescription` SQLAlchemy models (`app/core/db/models/job.py`)
- [x] T08 Implement `upsert_job()` with `ON CONFLICT DO UPDATE` on `dedup_hash`
- [x] T09 Implement `upsert_job_source()` with staleness tracking (`unconfirmed_count`)
- [x] T10 Implement `close_stale_jobs()`: increment counters, close jobs when all sources exceed threshold
- [x] T11 Implement `list_jobs_repo()` with keyword search and pagination

## Phase 4: Discovery Orchestrator

- [x] T12 Implement `run_discovery()` (`app/core/jdl/discovery.py`): crawl → normalize → upsert → close stale → refresh embeddings → company summaries → job descriptions
- [x] T13 Implement `DiscoveryResult` dataclass with counts (pages, created, updated, closed)

## Phase 5: Enrichment

- [x] T14 Implement `populate_company_summaries()` and `populate_for_companies()` with Tavily search (batched, retried)
- [x] T15 Implement `backfill_summaries_from_existing()` — copy summaries within same company (zero API cost)
- [x] T16 Implement `populate_job_descriptions()` with Jina AI content fetching (rate-limited, concurrent)

## Phase 6: Daemon

- [x] T17 Create `jdl_daemon.py` (`app/scripts/jdl_daemon.py`) with 12-hour ingestion loop
- [x] T18 Define `DISCOVERY_SEED_CRITERIA` — 7 default search queries in `seed_criteria.py`
- [x] T19 Integrate daemon into Docker Compose as `jdl-daemon` service with restart policy

## Gaps Identified

| Gap | Type | Recommendation |
|-----|------|----------------|
| ❌ No unit/integration tests | Test gap | Add `tests/test_jdl_client.py`, `tests/test_normalization.py`, `tests/test_discovery.py` with mock JDL API |
| ⚠️ Company summary exceptions caught broadly | Error handling | `discovery.py` lines 94-108 catch generic `Exception` — consider specific exception types |
| ℹ️ Seed criteria hardcoded | Config gap | Move seed criteria to config or env-driven JSON instead of Python module |
