# Feature Specification: JDL Client (Job Data Lake Integration)

**Status**: Migrated (reverse-engineered from code)
**Branch**: `phase4-infra-decoupling`
**Migrated**: 2026-07-10

## User Scenarios

### User Story 1 — Automated Job Ingestion (Priority: P1)

A background daemon periodically crawls the Job Data Lake API to discover new jobs, normalize them, and store them in the local database.

**Independent Test**: Run `run_discovery()` with a mock JDL client stub and verify jobs are upserted into the DB.

**Acceptance Scenarios**:

1. **Given** a configured `JOB_DATA_LAKE_API_KEY`, **When** the daemon runs a discovery cycle, **Then** new jobs are fetched, normalized, and stored
2. **Given** a job already exists in the DB, **When** the same job is discovered again, **Then** its `last_seen_at` is updated (not duplicated)
3. **Given** a job has not been seen for `unconfirmed_limit` consecutive cycles, **When** the daemon runs, **Then** the job is marked `closed`

### User Story 2 — Company Enrichment (Priority: P2)

Jobs discovered through the JDL API are enriched with company summaries from Tavily search and full job descriptions from Jina AI.

**Independent Test**: Mock Tavily/Jina responses and verify summaries and descriptions are saved to the correct job records.

**Acceptance Scenarios**:

1. **Given** a newly discovered job from a known company, **When** the discovery cycle completes, **Then** the job's `company_summary` is populated from existing records (zero API cost)
2. **Given** a newly discovered job from an unknown company, **When** the discovery cycle completes, **Then** a Tavily search is performed to generate a summary
3. **Given** a job with a `source_url`, **When** the discovery cycle completes, **Then** `JobDescription` is populated via Jina AI content fetch

### User Story 3 — Manual Job Search (Priority: P3)

Users can query the local job repository by keyword, browsing active jobs with pagination.

**Independent Test**: Call `list_jobs_repo()` with various keywords and verify filtered results and correct pagination.

**Acceptance Scenarios**:

1. **Given** multiple jobs in the DB, **When** searching by keyword, **Then** only matching active jobs are returned
2. **Given** a large number of jobs, **When** paginating, **Then** correct offsets and page sizes are applied

## Requirements

### Functional Requirements

- **FR-001**: System MUST authenticate with the JDL API using `X-Api-Key` header
- **FR-002**: System MUST rate-limit JDL API requests to 30 req/min
- **FR-003**: System MUST retry failed JDL requests (5xx) up to 3 times with exponential backoff
- **FR-004**: System MUST deduplicate jobs by SHA-256 hash of (company, title, skills)
- **FR-005**: System MUST normalize input: collapse whitespace, lowercase, deduplicate skills
- **FR-006**: System MUST upsert jobs by `dedup_hash` (create or update `last_seen_at`)
- **FR-007**: System MUST close jobs not seen for `unconfirmed_limit` (default: 2) consecutive cycles
- **FR-008**: System MUST support multiple date formats in incoming raw data (ISO 8601, Unix ms)
- **FR-009**: System MUST fetch company summaries via Tavily search with 4 retry attempts
- **FR-010**: System MUST fetch job descriptions via Jina AI with rate limiting (2 req/s, 3 concurrent)
- **FR-011**: System MUST run discovery daemon every 12 hours (configurable interval)
- **FR-012**: System MUST batch company summary fetches (batch size: 10)
- **FR-013**: System MUST batch job description fetches (batch size: 10)

### Key Entities

- **Job**: Core entity representing a job posting with metadata (title, company, skills, location, etc.)
- **JobSource**: Tracks a job's presence on an external source with staleness counter
- **JobDescription**: Full job description text fetched from Jina AI
- **JobSearchCriteria**: Search parameters for querying the JDL API

## Success Criteria

- **SC-001**: An 8-hour daemon run can ingest and persist jobs from all 7 seed criteria
- **SC-002**: Duplicate jobs (same company + title + skills) are never created as separate rows
- **SC-003**: Company summaries are backfilled from existing records when possible (zero API cost for repeats)
- **SC-004**: Job descriptions have 5 retry attempts with exponential jitter (initial 2s, max 60s)
- **SC-005**: Stale jobs are automatically closed within `unconfirmed_limit + 1` discovery cycles

## Assumptions

- JDL API is available at `https://api.jobdatalake.com/v1` with the documented schema
- Tavily API key is configured via `TAVILY_API_KEY` environment variable
- Jina AI endpoint `https://r.jina.ai/` is accessible with no auth required
- Date fields may arrive as ISO 8601 strings, Unix timestamps (seconds), or Unix millisecond timestamps
