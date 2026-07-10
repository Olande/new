# Quickstart: API Job Fallback Validation

**Feature**: `012-api-job-fallback` | **Date**: 2026-07-10

This guide documents **runnable validation scenarios** that prove the feature works
end-to-end. It is not an implementation guide — see [data-model.md](data-model.md) and
[plan.md](plan.md) for implementation details.

---

## Prerequisites

| Requirement | How to satisfy |
|-------------|----------------|
| Python 3.13+ | `python --version` |
| PostgreSQL running | `docker-compose up -d db` |
| Database migrated | `uv run alembic upgrade head` |
| `.env` configured | `JOB_DATA_LAKE_API_KEY`, `GOOGLE_API_KEY`, `POSTGRES_URL` set |
| Dependencies installed | `uv sync --frozen` |

---

## Setup Commands

```bash
# Start the PostgreSQL service (if not already running)
docker-compose up -d db

# Apply the api-job-fallback migration
uv run alembic upgrade head

# Verify the fallback_source column exists
psql $POSTGRES_URL -c "\d jobs" | grep fallback_source
# Expected: fallback_source   | character varying | ...

# Start the test suite to confirm baseline health
uv run pytest tests/ -v
```

---

## Scenario 1 — Empty Database → Fallback Triggered (US-1, FR-002, FR-004)

**Validates**: SC-001 (results within 10 s), FR-004 (three-step flow), FR-011 (attribution)

```bash
# Clear jobs table (test environment only)
psql $POSTGRES_URL -c "TRUNCATE jobs, job_sources, job_descriptions RESTART IDENTITY CASCADE;"

# Verify empty DB
psql $POSTGRES_URL -c "SELECT count(*) FROM jobs;"
# Expected: 0

# Run tests that exercise the fallback path
uv run pytest tests/test_fallback.py::test_empty_db_triggers_fallback -v

# Or run the MCP tool manually via the MCP inspector / direct HTTP
# Expected response: hits non-empty, fallback_used=true
```

**Expected outcome**:
- `fallback_used = true` in response
- `hits` contains jobs from JDL API (now stored in DB)
- `psql -c "SELECT count(*) FROM jobs WHERE fallback_source = 'jdl_api';"` > 0

---

## Scenario 2 — DB Populated → No Fallback (FR-001, FR-006, SC-002)

**Validates**: DB-only path is preserved when results are sufficient

```bash
# Confirm DB has sufficient jobs (from Scenario 1 or seed data)
psql $POSTGRES_URL -c "SELECT count(*) FROM jobs;"
# Expected: > fallback_min_result_threshold (default: 5)

# Run the same query again
uv run pytest tests/test_fallback.py::test_populated_db_no_fallback -v
```

**Expected outcome**:
- `fallback_used = false`
- Response time < 2 s (SC-002)
- No JDL API calls made (check logs: no "fallback" lines)

---

## Scenario 3 — Job ID Lookup via Fallback (US-2, FR-003)

**Validates**: Single-job lookup when ID absent from local DB

```bash
# Pick a known JDL job ID (from the JDL API docs or a prior search result)
export JDL_JOB_ID="<known-external-id>"

# Run the targeted test
uv run pytest tests/test_fallback.py::test_get_job_fallback -v
```

**Expected outcome**:
- Job returned with `fallback_source = "jdl_api"`
- Job now exists in local DB:
  ```bash
  psql $POSTGRES_URL -c "SELECT id, title FROM jobs WHERE fallback_source = 'jdl_api';"
  ```

---

## Scenario 4 — JDL API Unavailable → Graceful Degradation (FR-008, SC-003)

**Validates**: No crash when API is unreachable

```bash
# Run the mock-based test for API failure
uv run pytest tests/test_fallback.py::test_api_error_graceful -v
```

**Expected outcome**:
- No exception raised
- Response: `SearchJobsOutput(hits=[], total=0, fallback_used=False)`
- Log contains: `WARNING ... JDL fallback failed`

---

## Scenario 5 — In-Flight Deduplication (FR-013, SC-005)

**Validates**: Two simultaneous identical queries result in one API call

```bash
uv run pytest tests/test_fallback.py::test_inflight_dedup -v
```

**Expected outcome**:
- JDL API mock called exactly once
- Both callers receive results
- Log shows one "fallback triggered" and one "awaiting in-flight fallback"

---

## Scenario 6 — Malformed API Response → Per-Item Drop (FR-014)

**Validates**: Invalid jobs dropped, valid ones returned, count reported

```bash
uv run pytest tests/test_fallback.py::test_malformed_job_dropped -v
```

**Expected outcome**:
- `dropped_count = 1` (or N per test setup)
- Valid jobs still in `hits`
- No exception raised

---

## Scenario 7 — Migration Rollback Safety (FR spec: DB migration)

**Validates**: Migration can be cleanly applied and rolled back

```bash
# Apply
uv run alembic upgrade head
psql $POSTGRES_URL -c "\d jobs" | grep fallback_source  # must exist

# Rollback
uv run alembic downgrade -1
psql $POSTGRES_URL -c "\d jobs" | grep fallback_source  # must NOT exist

# Re-apply
uv run alembic upgrade head
```

**Expected outcome**: No errors at any step; column appears/disappears cleanly.

---

## Running All Fallback Tests

```bash
uv run pytest tests/test_fallback.py -v
```

| Test | FR | SC |
|------|----|----|
| `test_empty_db_triggers_fallback` | FR-002, FR-004 | SC-001 |
| `test_populated_db_no_fallback` | FR-001, FR-006 | SC-002 |
| `test_threshold_strict_lt` | FR-010 | — |
| `test_get_job_fallback` | FR-003 | — |
| `test_get_job_in_db_no_api` | FR-001 | — |
| `test_api_error_graceful` | FR-008 | SC-003 |
| `test_fallback_disabled` | FR-012 | — |
| `test_inflight_dedup` | FR-013 | SC-005 |
| `test_malformed_job_dropped` | FR-014 | — |

---

## Log Observability Reference

Every fallback event emits a structured loguru log:

```
INFO  | JobFallbackService | fallback triggered | query="python engineer" db_hits=0 api_results=15 latency_ms=432 dropped=0
WARN  | JobFallbackService | fallback rate limited | query="python engineer"
WARN  | JobFallbackService | fallback api error | query="python engineer" error="Connection timeout"
```

Check logs with: `grep -i "fallback" app.log`
