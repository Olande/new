# Feature Specification: API Job Fallback

**Feature Branch**: `012-api-job-fallback`

**Created**: 2026-07-10

**Status**: Refined

**Input**: User description: "Whenever the user asks for a job to be retrieved, the only possible way is to retrieve from the postgres database, but the problem is that the database is too sparse since it was only recently created, now with that if a user asks for a job most of the time he wont get the outcome, we need to invke the api to supplement cases where the database may nt have the required job"

## Project Context

This feature targets **CareerPilot AI** — a FastAPI + LangGraph + PostgreSQL (pgvector) backend.

| Module | Path | Purpose |
|--------|------|---------|
| Core | `app/core/` | Config, DB models, JDL client, LLM embeddings |
| Graph | `app/graph/` | LangGraph agent nodes, state, workflow |
| MCP | `app/mcp/` | MCP server, repositories, services |
| Retrieval | `app/retrieval/` | Hybrid search (BM25 + vector) |
| Evaluation | `app/evaluation/` | Metrics, HPO, eval runner |
| Scripts | `app/scripts/` | Background daemons (JDL) |

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Fallback Search When Database Returns No Results (Priority: P1)

When a user asks for job recommendations and the database contains no matching jobs (sparse or empty database), the system silently falls back to the JDL API to search for jobs matching the user's criteria.

**Why this priority**: This is the core value proposition — without fallback, users with sparse DB experience get zero results, rendering the system unusable. This story delivers the primary fix.

**Independent Test**: Can be fully tested by running a search query against a known-empty database and verifying that results are returned from the JDL API and presented to the user.

**Acceptance Scenarios**:

1. **Given** a database with zero job records, **When** a user submits a job search query (e.g., "software engineer remote"), **Then** the system fetches matching jobs from the JDL API and returns them to the user
2. **Given** a database with no results matching the user's criteria but non-empty job table, **When** a user submits a search, **Then** the system falls back to the JDL API and returns matched results
3. **Given** the JDL API returns results for a fallback search, **When** the results are presented to the user, **Then** each result includes clear source attribution (e.g., "retrieved from Job Data Lake")
4. **Given** the JDL API is unreachable or returns an error, **When** the fallback is triggered, **Then** the user receives a graceful message indicating no results were found (not an error)

---

### User Story 2 — Individual Job Lookup via API When ID Not in Database (Priority: P1)

When a user references a specific job (by ID or URL) that exists in the JDL data lake but has not yet been ingested into the local database, the system fetches that individual job on demand from the JDL API.

**Why this priority**: Users may reference jobs from external sources or from previous sessions after database resets. Without this fallback, a job that the system "should know about" returns "not found," degrading trust.

**Independent Test**: Can be tested by providing a known JDL job ID to the `get_job_tool` when that job is absent from the local database and verifying it is fetched from the JDL API and returned.

**Acceptance Scenarios**:

1. **Given** a job ID that exists in the JDL API but not in the local database, **When** a user requests that job by ID, **Then** the system fetches the job from the JDL API and returns its full details
2. **Given** a job ID that does not exist in either the database or the JDL API, **When** a user requests that job by ID, **Then** the system returns a "job not found" response (no fallback error)
3. **Given** a job ID that exists in the local database, **When** a user requests that job by ID, **Then** the system returns the local copy without calling the JDL API (no unnecessary network call)

---

### User Story 3 — Three-Step Fallback: API → Populate DB → Retrieve from DB (Priority: P2)

Jobs fetched via the JDL API fallback are never returned directly to the user. Instead, they are upserted into the local database first, then the system performs a second query against the local database so that all results (native + fallback) are ranked by the same hybrid search pipeline.

**Why this priority**: This ensures consistent ranking quality — every result the user sees, regardless of origin, passes through the same BM25 + vector + RRF scoring. It also populates the database for future queries. The trade-off is one additional DB round-trip per fallback invocation.

**Independent Test**: Can be tested by triggering a fallback and verifying that (1) the API is called, (2) results are upserted to DB, (3) a second DB query produces the final ranked result set, and (4) the user never receives raw API data directly.

**Acceptance Scenarios**:

1. **Given** a fallback search returned 3 jobs from the JDL API, **When** results are delivered, **Then** all 3 jobs are upserted into the local database **before** being returned
2. **Given** a fallback search upserted results into the DB, **When** the results are returned to the user, **Then** they are fetched from the local DB (second query) and ranked using the standard hybrid search pipeline
3. **Given** no fallback was triggered (DB had sufficient results), **When** results are returned, **Then** no API call is made and results follow the standard DB-only path (no change in behavior)
4. **Given** a job fetched via fallback has a dedup_hash matching an already-existing job, **When** upserted, **Then** the existing record is updated (not duplicated)
5. **Given** jobs are inserted via fallback, **When** ingested, **Then** they receive the same normalization and schema as batch-discovered jobs

---

### Edge Cases

- **Rate limit exhaustion**: The JDL client has a 30 req/60s rate limiter used by batch discovery. On-demand fallback must not starve the batch discovery pipeline. If rate limited, the fallback should gracefully return empty results and log a warning.
- **API key misconfiguration**: If the JDL API key is missing or invalid, fallback should be disabled silently (no crash). The system should log a warning and return database-only results.
- **Partial DB results**: If the database returns some results but strictly fewer than the supplementation threshold (e.g., < 50% of requested limit), the system supplements with JDL API results. At exactly the threshold, no API call is made (strict less-than). This threshold is configurable via settings.
- **Malformed or partial API response**: If the JDL API returns results where some jobs fail normalization (missing required fields, invalid data), those individual jobs are silently dropped and the remaining valid results are returned. The response includes a count of how many jobs were dropped due to data issues.
- **Duplicate fallback on rapid repeat queries**: If a user repeats the same query within seconds, the system should not make duplicate JDL API calls for jobs already being fetched or recently fetched. In-flight request deduplication or a short-lived cache of "fallback in progress" keys should prevent redundant API calls.
- **Large result sets from API fallback**: JDL API search may return many results. The system should limit the number of fallback results fetched to a reasonable maximum (e.g., 20 jobs) to avoid excessive latency.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST attempt database search first for all job retrieval operations (search by criteria and lookup by ID)
- **FR-002**: System MUST fall back to JDL API when database search returns zero results for a query-based job search
- **FR-003**: System MUST fall back to JDL API when a job ID lookup returns no match in the database
- **FR-004**: System MUST follow a three-step flow for all API fallback: (1) fetch jobs from JDL API, (2) upsert into local database (jobs, job_sources, job_descriptions tables), (3) re-query the local database to return results ranked by the standard hybrid search pipeline. Raw API results are never returned directly to the user.
- **FR-005**: System MUST normalize API-fetched jobs using the same normalization pipeline as batch-discovered jobs
- **FR-006**: System MUST NOT call the JDL API if the database already has matching results (no unnecessary API calls)
- **FR-007**: System MUST limit fallback API calls to a maximum of 20 result items per search fallback
- **FR-008**: System MUST handle JDL API errors (timeout, 5xx, rate limit) gracefully by returning empty results with appropriate user messaging
- **FR-014**: System MUST apply per-item error handling during API fallback: jobs that pass normalization are returned, jobs that fail are silently dropped, and the response includes a count of dropped jobs due to data issues
- **FR-009**: System MUST log every fallback API call with: query/ID, number of results fetched, latency, and success/failure status
- **FR-010**: System MUST support a configurable threshold for supplementing partial DB results, using strict less-than semantics (supplement only when DB results < threshold; at exactly the threshold, do not supplement)
- **FR-011**: System MUST include source attribution ("JDL Fallback") on jobs returned via API fallback so users and downstream logic can distinguish them from DB-native results
- **FR-012**: System MUST skip API fallback entirely when the JDL API key is not configured, logging a warning at startup
- **FR-013**: System MUST implement in-flight request deduplication for simultaneous identical fallback queries to prevent redundant API calls

### Key Entities *(include if feature involves data)*

- **JobSearchResult**: Existing Pydantic model for search results; extended with a `fallback_source` field to indicate API-originated results
- **JobDetailOutput**: Existing MCP output for full job details; extended with a `fallback_source` field
- **JDL Fallback Service**: New service layer that orchestrates the DB → API → upsert flow, mediating between the existing `JobDataLakeClient` (ingestion-only) and the retrieval layer
- **Fallback Configuration**: Configuration settings controlling fallback behavior (enabled/disabled, minimum result threshold, max fallback items, rate limit allocation)

### Database Migrations *(include if feature changes schema)*

- **Column changes**: Add nullable `fallback_source` VARCHAR column to `jobs` table to track which fallback mechanism (if any) retrieved the job
- **Indexes**: No new indexes required (uses existing PK and dedup_hash unique constraint)
- **Data migration**: No backfill needed — existing jobs have `fallback_source = NULL`
- **Migration command**: `uv run alembic revision --autogenerate -m "api-job-fallback"`
- **Rollback**: `uv run alembic downgrade -1`

### API Contract *(include if feature adds/modifies endpoints)*

**MCP Tools** (in `app/mcp/`):

| Tool Name | Service | Description |
|-----------|---------|-------------|
| `search_jobs_tool` | `app/mcp/services/job_service.py` | **Modified**: Add fallback to JDL API when DB returns no results |
| `get_job_tool` | `app/mcp/services/job_service.py` | **Modified**: Add fallback to JDL API when job ID not found in DB |

**Repository changes**:

- [x] Modified repository in `app/mcp/repositories/job_repo.py` (upsert methods for fallback results)
- [x] New service in `app/mcp/services/job_fallback_service.py` (fallback orchestration)
- [x] New or modified configuration in `app/core/config.py` (fallback settings)

### Graph Agent Changes *(include if feature modifies agent workflow)*

**New/Modified Nodes**:

| Node | File | Purpose |
|------|------|---------|
| `hybrid_search` | `app/graph/nodes.py` | **Modified**: Add three-step fallback path when DB returns zero or insufficient results — (1) call JDL fallback search, (2) upsert results to local DB, (3) re-run `search_jobs()` against the now-populated DB to return ranked results |

**State changes** (if needed):

- [ ] No new state fields required — existing `retrieved_jobs` and `extracted_criteria` suffice

**Workflow changes** (if needed):

- [ ] No routing changes required — the fallback is internal to the `hybrid_search` node

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A search query against an empty database returns results within 10 seconds (including JDL API call and upsert)
- **SC-002**: A repeated search for the same query returns results from database only, with zero API calls, within 2 seconds
- **SC-003**: The system never returns a hard error to the user due to JDL API unavailability — all API failures degrade to a "no results" message or graceful partial results
- **SC-004**: After 100 unique user queries, the database contains at least 75% of the jobs previously returned via fallback (self-population effectiveness)
- **SC-005**: In-flight deduplication prevents >95% of duplicate API calls for simultaneous identical queries
- **SC-006**: System logs every fallback API event with complete observability data (latency p50/p95, error rates, result counts)

## Assumptions

- The JDL API supports single-job lookup by ID as well as search by criteria — both capabilities are needed for the two fallback paths
- The existing JDL rate limiter (30 req/60s) is shared between on-demand fallback and batch discovery. If the pool is exhausted, fallback gracefully returns empty results. Contention under load is an acceptable trade-off for implementation simplicity; a dedicated rate pool can be introduced later if needed.
- Users with partial DB results (some but not enough) benefit from supplementation; the default threshold is 50% of the requested limit (configurable via `FALLBACK_MIN_RESULT_THRESHOLD`)
- The `JobDataLakeClient` can be reused for on-demand queries without modification to its core HTTP logic — only its invocation context changes
- Fallback-fetched jobs do not trigger subsequent discovery pipeline steps (company summaries, full description fetching, embedding generation) synchronously — those can happen asynchronously or on the next batch discovery cycle
- All fallback results are upserted to the DB and re-queried before returning to the user (never returned raw from API). This ensures consistent hybrid search ranking across all results.
- No additional security guardrails (daily caps, per-user rate limits) are placed on fallback beyond the shared JDL API rate limiter. The JDL API's own authentication and access controls are relied upon for abuse prevention.
- The existing dedup_hash mechanism on the `jobs` table is sufficient to prevent duplicate records when re-fetching already-stored jobs via fallback

## Brainstorm Log

### 2026-07-10 — Spec Review Session

**Insights discovered during brainstorming:**

1. **Supplementation threshold semantics** (Q1): Clarified that strict less-than (`< threshold`, not `≤ threshold`) governs when partial DB results trigger API fallback. At exactly the threshold, no API call is made.

2. **Per-item error handling** (Q2): When JDL API returns malformed data, individual failing jobs are silently dropped while valid ones are kept. The response includes a count of dropped jobs for transparency. (New FR-014.)

3. **Shared rate limiter** (Q3): Confirmed on-demand fallback and batch discovery share the single 30 req/60s pool. Contention under load is accepted for simplicity; a dedicated pool can be added later if needed.

4. **No additional guardrails** (Q4): Security relies on the JDL API's own authentication and access controls. No daily caps or per-user rate limits beyond the shared pool.

5. **Three-step fallback architecture** (Q5): Core architectural insight — fallback results are never returned raw from the JDL API. Instead, the flow is: (1) fetch from JDL API, (2) upsert into local DB, (3) re-query DB using standard hybrid search. This ensures all results receive consistent BM25 + vector + RRF ranking regardless of origin. (FR-004 updated; User Story 3 reworked.)

**New/Modified artifacts created during session:**

- FR-014 (new): Per-item error handling with dropped-count reporting
- FR-004 (updated): Three-step API → DB → query flow
- Edge Cases (updated): Malformed API response handling added
- Assumptions (updated): Shared rate pool, no guardrails, three-step ranking
- User Story 3 (reworked): From "populate DB" to "API → populate DB → retrieve from DB"
- Status: Draft → Refined
