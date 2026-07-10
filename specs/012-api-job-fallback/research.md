# Research: API Job Fallback

**Feature**: `012-api-job-fallback` | **Date**: 2026-07-10

## Overview

Research findings for all unknowns identified in the Technical Context of `plan.md`.
All NEEDS CLARIFICATION items are resolved below.

---

## R-001: JDL API Capabilities — Single-Job Lookup by ID

**Decision**: The existing `JobDataLakeClient` supports paginated **search** via `GET /v1/jobs`
and **single-job fetch** via `GET /v1/jobs/{id}`. Both capabilities are confirmed from
the JDL API contract used by `app/core/jdl/client.py`.

**Implementation**: Add `get_job_by_id(external_id: str)` to `JobDataLakeClient`:
```python
async def get_job_by_id(self, external_id: str) -> dict | None:
    async with self.limiter:
        response = await self.client.get(f"{BASE_URL}/jobs/{external_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
```

**Rationale**: HTTP 404 is not an error in this context — it means the job doesn't exist
in the data lake and the user gets a graceful "not found" response.

**Alternatives considered**: Polling search results to find by ID — rejected due to
high latency and unnecessary rate limiter consumption.

---

## R-002: Dedup Strategy for Fallback-Fetched Jobs

**Decision**: Rely on the existing `dedup_hash` unique constraint on `jobs.dedup_hash`
(SHA-256 of `{title}|{company_name}|{source_job_id}`). Use PostgreSQL's
`INSERT … ON CONFLICT (dedup_hash) DO UPDATE SET last_seen_at = NOW(), fallback_source = 'jdl_api'`
for upsert semantics.

**Rationale**: The existing batch discovery pipeline uses the same hash and constraint.
Re-using it means fallback jobs benefit from exactly the same deduplication guarantees
without introducing new unique keys or migration complexity.

**Alternatives considered**:
- New `jdl_job_id` column for lookup: adds migration complexity for a column that's
  already covered by `job_sources.source_job_id`. Rejected.
- Application-level dedup check before insert: race-prone under concurrent fallback requests.
  Rejected in favour of DB-level `ON CONFLICT`.

---

## R-003: asyncio In-Flight Request Deduplication Pattern

**Decision**: Use a module-level `dict[str, asyncio.Event]` keyed by `sha256(normalized_query)`.
The first coroutine to reach the fallback path sets an Event; subsequent ones for the
same key `await` that Event before re-querying the DB (which will now have the results
the first waiter upserted).

```python
_in_flight: dict[str, asyncio.Event] = {}

async def _deduped_fetch(query_key: str, fetch_coro):
    if query_key in _in_flight:
        await _in_flight[query_key].wait()
        return  # results now in DB
    event = asyncio.Event()
    _in_flight[query_key] = event
    try:
        await fetch_coro()
    finally:
        event.set()
        _in_flight.pop(query_key, None)
```

**Rationale**: `asyncio.Event` is the idiomatic single-process deduplication primitive.
Since the MCP server runs in a single asyncio event loop (not multi-process), this is
sufficient. Satisfies FR-013 and SC-005 (>95% dedup effectiveness).

**Alternatives considered**:
- Redis-based distributed lock: over-engineered for a single-process server. Rejected.
- `asyncio.Lock` per query: prevents parallel execution even for *different* queries.
  Rejected.

---

## R-004: Embedding Generation for Fallback-Upserted Jobs

**Decision**: Do **not** generate embeddings synchronously during the fallback path.
Instead, schedule embedding generation as a fire-and-forget `asyncio.create_task()`.
The second DB query (step 3 of the three-step flow) is run immediately after upsert,
and jobs without embeddings will score lower in hybrid search (BM25 only). This is
acceptable for the first query; embeddings will be available by the time the user queries again.

**Rationale**: Synchronous embedding generation during a user-facing request adds 500 ms–2 s
of latency per job and may exceed the 10 s SC-001 target for large fallback result sets.
Fire-and-forget is the correct trade-off: the user gets results fast, embeddings arrive
shortly after.

**Alternatives considered**:
- Block on embedding generation: latency risk. Rejected.
- Background daemon picks up new jobs: correct long-term, but adds delay before any
  hybrid search score. Fire-and-forget is a good middle ground.

---

## R-005: JDL Rate Limiter Sharing Strategy

**Decision**: The existing `AsyncLimiter(30, 60)` in `JobDataLakeClient` is shared between
batch discovery and on-demand fallback. No changes to the limiter are made.

**Handling**: When the limiter raises `aiolimiter.RateLimitError` (or the request times out),
`JobFallbackService` catches the exception, logs a `WARNING`, and returns the DB-only results
(which may be empty). The user receives a graceful "no results found" message.

**Rationale**: The spec explicitly accepts contention as a trade-off for simplicity
(see Assumptions). A dedicated rate pool can be added later if monitoring shows
fallback starvation.

---

## R-006: Normalization Pipeline Reuse

**Decision**: Reuse `app/core/jdl/normalization.normalize_job(raw_dict) -> NormalizedJob`
directly in `JobFallbackService`. The function is already used by the batch discovery
pipeline and handles: whitespace collapsing, skill normalization, dedup hash computation,
`posted_at` parsing, and `status` defaulting.

**Key finding**: `normalize_job` returns a `NormalizedJob` dataclass (not a SQLAlchemy
model). The new `upsert_from_fallback()` in `JobRepository` must map this dataclass to
the `Job` ORM model before inserting.

---

## R-007: MCP Schema Backward Compatibility

**Decision**: All new fields on MCP output schemas use `= None` or `= False` defaults.
Existing callers (the LangGraph agent, tests) receive the same structure as before —
new fields are additive and backwards-compatible.

No versioning bump to the MCP protocol is required.

---

## Summary Table

| Unknown | Decision |
|---------|----------|
| JDL single-job lookup | `GET /v1/jobs/{id}` — add `get_job_by_id()` to client |
| Dedup strategy | Existing `dedup_hash` + `ON CONFLICT DO UPDATE` |
| In-flight dedup | `asyncio.Event` per query hash, module-level dict |
| Embedding timing | Fire-and-forget after upsert, not blocking |
| Rate limiter | Shared pool; `RateLimitError` → graceful empty result |
| Normalization | Reuse `normalize_job()` directly |
| Schema compat | Additive fields with safe defaults |
