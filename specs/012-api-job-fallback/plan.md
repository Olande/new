# Implementation Plan: API Job Fallback

**Branch**: `012-api-job-fallback` | **Date**: 2026-07-10 | **Spec**: [spec.md](spec.md)

## Summary

Implement a transparent three-step fallback mechanism for job retrieval. When the local
PostgreSQL database returns zero (or insufficient) results, the system calls the JDL API,
upserts the returned jobs into the database using the same normalization pipeline as batch
discovery, then re-queries the database via the standard hybrid search pipeline before
returning results to the user. Raw API data is **never** returned directly. The same
fallback applies to single-job lookups by ID.

## Technical Context

- **Language/Version**: Python 3.13+
- **Primary Dependencies**: `httpx`, `aiolimiter`, `sqlalchemy` (async), `loguru`, `pydantic`, `asyncpg`, `pgvector`
- **Testing**: `pytest`, `pytest-asyncio` — `uv run pytest tests/`
- **Project Type**: Backend API service + MCP server + LangGraph agent
- **Performance Goals**: Cold fallback returns results within 10 s (SC-001); DB-only path within 2 s (SC-002)
- **Constraints**: PostgreSQL + pgvector, MCP protocol, shared JDL rate limiter (30 req/60 s)
- **Scale/Scope**: ~10 k jobs, 100 users, single-region

## Constitution Check

*GATE: Passes all constitution checks.*

- ✅ **I. Decoupled Architecture**: New logic lives in `job_fallback_service.py`; existing layers unchanged
- ✅ **II. Deterministic Vector Search**: Embeddings generated after upsert via existing pipeline
- ✅ **III. Rigorous Testing**: Unit tests in `tests/test_fallback.py` with full mock coverage
- ✅ **IV. Input Normalization**: Fallback jobs use same `normalize_job()` as batch discovery
- ✅ **V. Observability**: Structured log per fallback event (FR-009, SC-006)
- ✅ **VI. Framework-First**: Reuses `JobDataLakeClient`, `normalize_job`, existing repo
- ✅ **VIII. Simplicity**: Thin orchestration over existing components, no new frameworks

## Proposed Changes

### Phase A — Settings & Model (foundation)

**`app/core/config/settings.py`** — add 3 new fields:

```python
fallback_enabled: bool = True
fallback_min_result_threshold: int = 5   # supplement when DB hits < this value
fallback_max_results: int = 20           # cap on JDL API results per call
```

**`app/core/db/models/job.py`** — add column to `Job`:

```python
fallback_source: Mapped[str | None] = mapped_column(String, nullable=True)
```

**Alembic migration** (`uv run alembic revision --autogenerate -m "api-job-fallback"`):
```sql
ALTER TABLE jobs ADD COLUMN fallback_source VARCHAR;
```
No backfill needed — existing rows get NULL (not from fallback).

---

### Phase B — Repository (data access)

**`app/mcp/repositories/job_repo.py`** — add 2 methods:

1. `async upsert_from_fallback(jobs: list[NormalizedJob]) -> list[Job]`
   - Uses `INSERT … ON CONFLICT (dedup_hash) DO UPDATE` (PostgreSQL dialect)
   - Sets `fallback_source = "jdl_api"` and refreshes `last_seen_at`
   - Returns upserted ORM objects for downstream embedding scheduling

2. `async get_by_source_job_id(source_job_id: str) -> Job | None`
   - Joins `job_sources` on `source_job_id` to check if a JDL job is already stored

---

### Phase C — Fallback Service (core orchestration)

**`app/mcp/services/job_fallback_service.py`** — NEW file (the core piece):

```
JobFallbackService
  _in_flight: dict[str, asyncio.Event]   # per-query-key dedup

  search_with_fallback(query, limit, threshold, criteria) -> SearchJobsOutput
    1. db_hits = await job_repo.search(query, limit, threshold)
    2. if len(db_hits) < settings.fallback_min_result_threshold:
         [in-flight dedup check / set]
         api_jobs = await _fetch_from_jdl(criteria, max=fallback_max_results)
         valid, dropped = _normalize_and_filter(api_jobs)
         upserted = await job_repo.upsert_from_fallback(valid)
         _schedule_embeddings(upserted)       # fire-and-forget asyncio.create_task
         db_hits = await job_repo.search(query, limit, threshold)  # 2nd query
         [clear in-flight]
    3. return SearchJobsOutput(hits=..., fallback_used=True, dropped_count=dropped)

  get_job_with_fallback(job_id: UUID) -> JobDetailOutput
    1. job = await job_repo.get_by_id(job_id)
    2. if job is None and fallback_enabled:
         raw = await _fetch_single_from_jdl(external_id_for(job_id))
         if raw: upsert and re-fetch from DB
    3. return map_to_JobDetailOutput(job, fallback_source)
```

**Key implementation rules**:
- `asyncio.Event` per `query_key = sha256(query.lower().strip())` for dedup (FR-013)
- If `settings.fallback_enabled is False` → return DB-only results, no API call (FR-012)
- Catch `httpx.HTTPError`, `aiolimiter.RateLimitError` → empty results + `logger.warning()` (FR-008)
- `dropped_count` tracked per individual normalization failure (FR-014)
- Strict `<` threshold: `len(db_hits) < settings.fallback_min_result_threshold` (FR-010)
- JDL client init wrapped in try/except; sets `fallback_enabled=False` if key missing

---

### Phase D — MCP Service update

**`app/mcp/services/job_service.py`** — `search_jobs()` and `get_job()` delegate to
`JobFallbackService` instead of calling `JobRepository` directly.

---

### Phase E — Graph Node update

**`app/graph/nodes.py`** — `hybrid_search` node uses `JobFallbackService.search_with_fallback()`
instead of bare `search_jobs()`. No routing changes; fallback is internal to the node.

---

### Phase F — Output Schema Extensions

**`app/mcp/mcp_schemas.py`**:

| Model | New Field | Type | Notes |
|-------|-----------|------|-------|
| `JobHit` | `fallback_source` | `str \| None = None` | Source attribution (FR-011) |
| `SearchJobsOutput` | `fallback_used` | `bool = False` | Indicates fallback triggered |
| `SearchJobsOutput` | `dropped_count` | `int = 0` | Per-item error count (FR-014) |
| `JobDetailOutput` | `fallback_source` | `str \| None = None` | Source attribution |

## Verification Plan

### Automated Tests (`tests/test_fallback.py`)

| Test ID | Scenario | Key Assertion |
|---------|----------|---------------|
| T001 | DB hits ≥ threshold | No JDL API call, results returned |
| T002 | DB hits < threshold | API called, upsert + re-query runs |
| T003 | DB empty (0 hits) | Three-step flow completes, results returned |
| T004 | API returns 5xx error | Graceful empty result, no exception |
| T005 | `fallback_enabled=False` | API never called regardless of DB results |
| T006 | Two simultaneous identical queries | Second waits on Event, one API call total |
| T007 | API returns malformed job | Item dropped, `dropped_count=1` |
| T008 | `job_id` already in DB | Returned without API call |
| T009 | `job_id` absent from DB | Fetched from API, upserted, returned |

### Migration Verification

```bash
uv run alembic upgrade head
uv run alembic downgrade -1   # verify rollback
uv run alembic upgrade head   # re-apply
```

### Manual Smoke Test

```bash
# 1. Start with empty DB, run MCP server
uv run python -m app.mcp.mcp_server

# 2. Issue search (triggers fallback)
# Expect: jobs returned, fallback_used=true, latency < 10s

# 3. Repeat same query (hits DB cache)
# Expect: fallback_used=false, latency < 2s

# 4. Verify DB populated
psql -c "SELECT count(*) FROM jobs WHERE fallback_source = 'jdl_api';"
```
