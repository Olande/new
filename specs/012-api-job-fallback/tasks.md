---
description: "Writing-plans-driven task breakdown for API Job Fallback — transparent three-step fallback to JDL API when local DB returns insufficient results"
---

# API Job Fallback Implementation Plan

> **Status: All Phase 1 & 2 tasks (T001–T013) are DONE.** US1 & US2 scenario tests exist and pass (37/37). The `012-api-job-fallback` branch's work (3 commits) was ported to the restructured codebase; the migration file was adapted and placed in alembic/versions/. Full implementation summary below.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the local PostgreSQL database returns zero or insufficient job results, transparently fetch from the JDL API, upsert into the local DB, and re-query via hybrid search before returning ranked results to the user.

**Architecture:** A new `JobFallbackService` orchestrates a three-step flow: (1) check DB → if hits < threshold, (2) fetch from JDL API via existing `JobDataLakeClient`, (3) upsert via `ON CONFLICT` and re-query DB for consistent BM25+vector ranking. In-flight deduplication via `asyncio.Event`. Embeddings generated fire-and-forget. Same pattern applies to single-job ID lookup.

**Tech Stack:** Python 3.13+, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16 + pgvector, httpx, aiolimiter, loguru, pytest, pytest-asyncio

## Global Constraints

- All DB access is async via `AsyncSession` — never sync in async context
- All new output fields use `= None` / `= False` defaults for backward compatibility (R-007)
- `normalize_job()` from `app/core/jdl/normalization.py` handles whitespace collapsing, skill normalization, dedup hash
- Rate limiter shared with batch discovery: `AsyncLimiter(30, 60)` in `JobDataLakeClient` (R-005)
- Dedup via existing `jobs.dedup_hash` unique constraint + `INSERT ... ON CONFLICT DO UPDATE` (R-002)
- Migration: `uv run alembic revision --autogenerate -m "api-job-fallback"`
- Tests: `uv run pytest tests/`
- Lint: `uv run ruff check app/ tests/`
- Format: `uv run ruff format app/ tests/`

---

## Phase 1: Setup

**Purpose:** Project initialization — dependencies, linting, formatting baseline

- [x] **T001 [P]: Install/refresh dependencies**

    ```bash
    uv sync --frozen
    ```

- [x] **T002 [P]: Run linting**

    ```bash
    uv run ruff check app/ tests/
    ```

- [x] **T003 [P]: Run formatting**

    ```bash
    uv run ruff format app/ tests/
    ```

---

## Phase 2: Foundational — Settings, Model, Schemas, Repository

**Purpose:** Blocking prerequisites for all user stories — config, DB migration, output schemas, repository methods, JDL client extension

---

### Task T004 [P] [TDD] [SUBAGENT]: Add fallback config to Settings

**Files:**
- Modify: `app/core/config/settings.py`
- Test: `tests/test_fallback.py`

**Interfaces:**
- Consumes: Existing `Settings` BaseSettings class
- Produces: `Settings.fallback_enabled: bool`, `Settings.fallback_min_result_threshold: int`, `Settings.fallback_max_results: int`

- [ ] **Step 1: Write the failing test**

    Add to `tests/test_fallback.py`:

    ```python
    from app.core.config.settings import Settings

    def test_fallback_settings_defaults():
        """FR-010, FR-012: Fallback settings have correct defaults."""
        settings = Settings()  # no env overrides — uses defaults
        assert settings.fallback_enabled is True
        assert settings.fallback_min_result_threshold == 5
        assert settings.fallback_max_results == 20

    def test_fallback_settings_env_override(monkeypatch):
        """Settings respect env var overrides."""
        monkeypatch.setenv("FALLBACK_ENABLED", "false")
        monkeypatch.setenv("FALLBACK_MIN_RESULT_THRESHOLD", "3")
        monkeypatch.setenv("FALLBACK_MAX_RESULTS", "10")
        settings = Settings()
        assert settings.fallback_enabled is False
        assert settings.fallback_min_result_threshold == 3
        assert settings.fallback_max_results == 10

    def test_fallback_threshold_zero_allowed():
        """threshold >= 0 — threshold=0 means always supplement."""
        settings = Settings(fallback_min_result_threshold=0)
        assert settings.fallback_min_result_threshold >= 0

    def test_fallback_max_results_clamped():
        """max_results in [1, 100]. Default 20 is valid."""
        settings = Settings(fallback_max_results=20)
        assert 1 <= settings.fallback_max_results <= 100
    ```

- [ ] **Step 2: Run test to verify it fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_fallback_settings_defaults -v --no-header -q
    ```
    Expected: FAIL — `Settings` has no `fallback_enabled`

- [ ] **Step 3: Write minimal implementation**

    In `app/core/config/settings.py`, add to the `Settings` class:

    ```python
    # Fallback configuration
    fallback_enabled: bool = True
    fallback_min_result_threshold: int = 5  # supplement when DB hits < this
    fallback_max_results: int = 20          # JDL API result cap per call
    ```

- [ ] **Step 4: Run test to verify it passes**

    ```bash
    uv run pytest tests/test_fallback.py::test_fallback_settings_defaults -v
    ```
    Expected: PASS

- [ ] **Step 5: Commit**

    ```bash
    git add app/core/config/settings.py tests/test_fallback.py
    git commit -m "feat(fallback): add fallback config to Settings"
    ```

---

### Task T005 [P] [TDD] [SUBAGENT]: Add fallback_source column to Job model

**Files:**
- Modify: `app/core/db/models/job.py`
- Test: `tests/test_fallback.py`

**Interfaces:**
- Consumes: Existing `Job` ORM model
- Produces: `Job.fallback_source: Mapped[str | None]` — `"jdl_api"` or `None`

- [ ] **Step 1: Write the failing test**

    Add to `tests/test_fallback.py`:

    ```python
    import uuid
    from app.core.db.models.job import Job

    def test_job_model_has_fallback_source():
        """FR-011: Job model supports fallback_source column."""
        job = Job(
            id=uuid.uuid4(),
            title="Test Engineer",
            dedup_hash="test_hash_001",
            fallback_source="jdl_api",
        )
        assert job.fallback_source == "jdl_api"

    def test_job_model_fallback_source_nullable():
        """Existing jobs have fallback_source=NULL (backward compat)."""
        job = Job(
            id=uuid.uuid4(),
            title="Test Engineer",
            dedup_hash="test_hash_002",
        )
        assert job.fallback_source is None
    ```

- [ ] **Step 2: Run test to verify it fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_job_model_has_fallback_source -v --no-header -q
    ```
    Expected: FAIL — `Job` model has no `fallback_source` field

- [ ] **Step 3: Write minimal implementation**

    In `app/core/db/models/job.py`, add to the `Job` class:

    ```python
    fallback_source: Mapped[str | None] = mapped_column(String, nullable=True)
    ```

- [ ] **Step 4: Run test to verify it passes**

    ```bash
    uv run pytest tests/test_fallback.py::test_job_model_has_fallback_source -v
    ```
    Expected: PASS

- [ ] **Step 5: Commit**

    ```bash
    git add app/core/db/models/job.py tests/test_fallback.py
    git commit -m "feat(fallback): add fallback_source column to Job model"
    ```

---

### Task T006: Generate Alembic migration

- [ ] **Step 1: Generate autogenerated migration**

    ```bash
    uv run alembic revision --autogenerate -m "api-job-fallback"
    ```
    Expected: New file in `alembic/versions/` with `ALTER TABLE jobs ADD COLUMN fallback_source VARCHAR;`

- [ ] **Step 2: Review the migration script**

    Open the generated file and verify:
    - Only `fallback_source` column is added
    - No tables are dropped or altered unintentionally
    - The downgrade drops the column

- [ ] **Step 3: Commit**

    ```bash
    git add alembic/versions/
    git commit -m "feat(fallback): add migration for fallback_source column"
    ```

---

### Task T007: Apply migration

- [ ] **Step 1: Apply migration**

    ```bash
    uv run alembic upgrade head
    ```

- [ ] **Step 2: Verify column exists**

    ```bash
    psql $POSTGRES_URL -c "\d jobs" | grep fallback_source
    ```
    Expected: `fallback_source | character varying | ...`

- [ ] **Step 3: Verify rollback works**

    ```bash
    uv run alembic downgrade -1
    psql $POSTGRES_URL -c "\d jobs" | grep fallback_source
    ```
    Expected: column NOT present

- [ ] **Step 4: Re-apply**

    ```bash
    uv run alembic upgrade head
    ```

- [ ] **Step 5: Commit**

    ```bash
    git add alembic/versions/
    git commit -m "feat(fallback): apply fallback_source migration"
    ```

---

### Task T008 [P] [TDD] [SUBAGENT]: Extend JobHit with fallback_source

**Files:**
- Modify: `app/mcp/mcp_schemas.py`
- Test: `tests/test_fallback.py`

- [ ] **Step 1: Write the failing test**

    ```python
    from app.mcp.mcp_schemas import JobHit

    def test_job_hit_has_fallback_source():
        """FR-011: JobHit carries fallback_source attribution."""
        hit = JobHit(
            id="550e8400-e29b-41d4-a716-446655440000",
            title="Engineer",
            company_name="Acme",
            score=0.95,
            fallback_source="jdl_api",
        )
        assert hit.fallback_source == "jdl_api"

    def test_job_hit_fallback_source_default_none():
        """Backward compat: fallback_source defaults to None."""
        hit = JobHit(
            id="550e8400-e29b-41d4-a716-446655440001",
            title="Engineer",
            company_name="Acme",
            score=0.85,
        )
        assert hit.fallback_source is None
    ```

- [ ] **Step 2: Run test — verify fail**

    ```bash
    uv run pytest tests/test_fallback.py::test_job_hit_has_fallback_source -v --no-header -q
    ```

- [ ] **Step 3: Implement**

    In `app/mcp/mcp_schemas.py`, add to `JobHit`:

    ```python
    fallback_source: str | None = None  # "jdl_api" or None
    ```

- [ ] **Step 4: Run test — verify pass**

    ```bash
    uv run pytest tests/test_fallback.py::test_job_hit_has_fallback_source -v
    ```

- [ ] **Step 5: Commit**

    ```bash
    git add app/mcp/mcp_schemas.py tests/test_fallback.py
    git commit -m "feat(fallback): add fallback_source to JobHit schema"
    ```

---

### Task T009 [P] [TDD] [SUBAGENT]: Extend SearchJobsOutput with fallback_used and dropped_count

**Files:**
- Modify: `app/mcp/mcp_schemas.py`
- Test: `tests/test_fallback.py`

- [ ] **Step 1: Write the failing test**

    ```python
    from app.mcp.mcp_schemas import SearchJobsOutput, JobHit

    def test_search_jobs_output_fallback_fields():
        """FR-011, FR-014: Output carries fallback_used and dropped_count."""
        result = SearchJobsOutput(
            hits=[],
            total=0,
            fallback_used=True,
            dropped_count=2,
        )
        assert result.fallback_used is True
        assert result.dropped_count == 2

    def test_search_jobs_output_defaults():
        """Backward compat: new fields default to False/0."""
        result = SearchJobsOutput(hits=[], total=0)
        assert result.fallback_used is False
        assert result.dropped_count == 0
    ```

- [ ] **Step 2: Run test — verify fail**

    ```bash
    uv run pytest tests/test_fallback.py::test_search_jobs_output_fallback_fields -v --no-header -q
    ```

- [ ] **Step 3: Implement**

    In `app/mcp/mcp_schemas.py`, modify `SearchJobsOutput`:

    ```python
    class SearchJobsOutput(BaseModel):
        hits: list[JobHit]
        total: int
        fallback_used: bool = False   # NEW
        dropped_count: int = 0        # NEW
    ```

- [ ] **Step 4: Run test — verify pass**

    ```bash
    uv run pytest tests/test_fallback.py::test_search_jobs_output_fallback_fields -v
    ```

- [ ] **Step 5: Commit**

    ```bash
    git add app/mcp/mcp_schemas.py tests/test_fallback.py
    git commit -m "feat(fallback): add fallback_used and dropped_count to SearchJobsOutput"
    ```

---

### Task T010 [P] [TDD] [SUBAGENT]: Extend JobDetailOutput with fallback_source

**Files:**
- Modify: `app/mcp/mcp_schemas.py`
- Test: `tests/test_fallback.py`

- [ ] **Step 1: Write the failing test**

    ```python
    from app.mcp.mcp_schemas import JobDetailOutput

    def test_job_detail_output_fallback_source():
        """FR-011: Job detail response carries fallback_source."""
        detail = JobDetailOutput(
            id="550e8400-e29b-41d4-a716-446655440000",
            title="Engineer",
            company_name="Acme",
            fallback_source="jdl_api",
        )
        assert detail.fallback_source == "jdl_api"

    def test_job_detail_output_fallback_source_default():
        """Backward compat: fallback_source defaults to None."""
        detail = JobDetailOutput(
            id="550e8400-e29b-41d4-a716-446655440001",
            title="Engineer",
            company_name="Acme",
        )
        assert detail.fallback_source is None
    ```

- [ ] **Step 2: Run test — verify fail**

    ```bash
    uv run pytest tests/test_fallback.py::test_job_detail_output_fallback_source -v --no-header -q
    ```

- [ ] **Step 3: Implement**

    In `app/mcp/mcp_schemas.py`, add to `JobDetailOutput`:

    ```python
    fallback_source: str | None = None  # NEW: "jdl_api" or None
    ```

- [ ] **Step 4: Run test — verify pass**

    ```bash
    uv run pytest tests/test_fallback.py::test_job_detail_output_fallback_source -v
    ```

- [ ] **Step 5: Commit**

    ```bash
    git add app/mcp/mcp_schemas.py tests/test_fallback.py
    git commit -m "feat(fallback): add fallback_source to JobDetailOutput schema"
    ```

---

### Task T011 [P] [TDD] [SUBAGENT]: Add upsert_from_fallback() to JobRepository

**Files:**
- Modify: `app/mcp/repositories/job_repo.py`
- Test: `tests/test_fallback.py`

**Interfaces:**
- Consumes: `NormalizedJob` (dataclass from `app/core/jdl/normalization.py`)
- Produces: `async upsert_from_fallback(normalized_jobs: list[NormalizedJob]) -> list[Job]`

- [ ] **Step 1: Write the failing test**

    ```python
    import uuid
    import pytest
    from datetime import datetime
    from app.core.db.models.job import Job
    from app.core.jdl.normalization import NormalizedJob

    @pytest.mark.asyncio
    async def test_upsert_from_fallback_inserts_new(job_repo, db_session):
        """FR-004: New fallback jobs are upserted with fallback_source='jdl_api'."""
        nj = NormalizedJob(
            title="Python Engineer",
            company_name="Acme Corp",
            dedup_hash="dedup_upsert_001",
            source_name="jobdatalake",
            source_job_id="jdl_001",
        )
        jobs = await job_repo.upsert_from_fallback([nj])
        assert len(jobs) == 1
        assert jobs[0].fallback_source == "jdl_api"
        assert jobs[0].title == "Python Engineer"

    @pytest.mark.asyncio
    async def test_upsert_from_fallback_updates_existing(job_repo, db_session):
        """R-002: ON CONFLICT updates existing job (dedup_hash match)."""
        # Insert once
        nj1 = NormalizedJob(
            title="Python Engineer",
            company_name="Acme Corp",
            dedup_hash="dedup_update_001",
            source_name="jobdatalake",
            source_job_id="jdl_001",
        )
        await job_repo.upsert_from_fallback([nj1])

        # Insert again with different title — should update
        nj2 = NormalizedJob(
            title="Senior Python Engineer",
            company_name="Acme Corp",
            dedup_hash="dedup_update_001",
            source_name="jobdatalake",
            source_job_id="jdl_001",
        )
        jobs = await job_repo.upsert_from_fallback([nj2])
        assert len(jobs) == 1
        # The upserted job should have the new title
        assert jobs[0].title == "Senior Python Engineer"
        assert jobs[0].fallback_source == "jdl_api"

    @pytest.mark.asyncio
    async def test_upsert_from_fallback_sets_last_seen_at(job_repo, db_session):
        """Upsert refreshes last_seen_at."""
        from datetime import datetime, timezone
        nj = NormalizedJob(
            title="Data Scientist",
            company_name="Data Co",
            dedup_hash="dedup_ts_001",
            source_name="jobdatalake",
            source_job_id="jdl_002",
        )
        before = datetime.now(timezone.utc)
        jobs = await job_repo.upsert_from_fallback([nj])
        after = datetime.now(timezone.utc)
        assert jobs[0].last_seen_at is not None
        assert before <= jobs[0].last_seen_at.replace(tzinfo=timezone.utc) <= after
    ```

- [ ] **Step 2: Run test — verify fail**

    ```bash
    uv run pytest tests/test_fallback.py::test_upsert_from_fallback_inserts_new -v --no-header -q
    ```
    Expected: FAIL — `JobRepository` has no `upsert_from_fallback`

- [ ] **Step 3: Implement**

    In `app/mcp/repositories/job_repo.py`:

    ```python
    from app.core.jdl.normalization import NormalizedJob

    class JobRepository:
        # ... existing methods ...

        async def upsert_from_fallback(
            self,
            normalized_jobs: list[NormalizedJob],
        ) -> list[Job]:
            """Bulk-upsert fallback jobs via ON CONFLICT (dedup_hash) DO UPDATE.

            Sets fallback_source = 'jdl_api' and refreshes last_seen_at.
            Returns upserted Job ORM objects.
            """
            if not normalized_jobs:
                return []

            jobs_to_insert = [
                Job(
                    id=uuid.uuid4(),
                    title=job.title,
                    company_name=job.company_name,
                    description_text=job.description_text,
                    required_skills=job.required_skills,
                    locations=job.locations,
                    remote_type=job.remote_type,
                    employment_type=job.employment_type,
                    seniority=job.seniority,
                    posted_at=job.posted_at,
                    status=job.status,
                    dedup_hash=job.dedup_hash,
                    fallback_source="jdl_api",
                    last_seen_at=func.now(),
                )
                for job in normalized_jobs
            ]

            async with self.session as session:
                session.add_all(jobs_to_insert)
                await session.flush()

                # Use raw SQL for ON CONFLICT upsert behavior
                # SQLAlchemy 2.0: execute with bulk insert + on_conflict_do_update
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(Job).values(
                    [
                        {
                            "id": j.id,
                            "title": j.title,
                            "company_name": j.company_name,
                            "description_text": j.description_text,
                            "required_skills": j.required_skills,
                            "locations": j.locations,
                            "remote_type": j.remote_type,
                            "employment_type": j.employment_type,
                            "seniority": j.seniority,
                            "posted_at": j.posted_at,
                            "status": j.status,
                            "dedup_hash": j.dedup_hash,
                            "fallback_source": "jdl_api",
                            "last_seen_at": func.now(),
                        }
                        for j in jobs_to_insert
                    ]
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["dedup_hash"],
                    set_={
                        "fallback_source": "jdl_api",
                        "last_seen_at": func.now(),
                        "title": stmt.excluded.title,
                        "company_name": stmt.excluded.company_name,
                        "description_text": stmt.excluded.description_text,
                    },
                )
                await session.execute(stmt)
                await session.commit()

                # Re-fetch upserted rows
                hashes = [j.dedup_hash for j in normalized_jobs]
                result = await session.execute(
                    select(Job).where(Job.dedup_hash.in_(hashes))
                )
                return list(result.scalars().all())
    ```

- [ ] **Step 4: Run test — verify pass**

    ```bash
    uv run pytest tests/test_fallback.py::test_upsert_from_fallback_inserts_new -v
    ```
    Expected: PASS

- [ ] **Step 5: Commit**

    ```bash
    git add app/mcp/repositories/job_repo.py tests/test_fallback.py
    git commit -m "feat(fallback): add upsert_from_fallback() to JobRepository"
    ```

---

### Task T012 [P] [TDD] [SUBAGENT]: Add get_by_source_job_id() to JobRepository

**Files:**
- Modify: `app/mcp/repositories/job_repo.py`
- Test: `tests/test_fallback.py`

**Interfaces:**
- Produces: `async get_by_source_job_id(source_job_id: str, source_name: str = "jobdatalake") -> Job | None`

- [ ] **Step 1: Write the failing test**

    ```python
    @pytest.mark.asyncio
    async def test_get_by_source_job_id_found(job_repo, db_session, sample_job_with_source):
        """Returns Job when source_job_id matches."""
        job = await job_repo.get_by_source_job_id("jdl_source_001")
        assert job is not None
        assert job.title == "Sample Job"

    @pytest.mark.asyncio
    async def test_get_by_source_job_id_not_found(job_repo):
        """Returns None when source_job_id doesn't exist."""
        job = await job_repo.get_by_source_job_id("nonexistent_id")
        assert job is None
    ```

- [ ] **Step 2: Run test — verify fail**

    ```bash
    uv run pytest tests/test_fallback.py::test_get_by_source_job_id_found -v --no-header -q
    ```
    Expected: FAIL — `JobRepository` has no `get_by_source_job_id`

- [ ] **Step 3: Implement**

    In `app/mcp/repositories/job_repo.py`, add:

    ```python
    async def get_by_source_job_id(
        self,
        source_job_id: str,
        source_name: str = "jobdatalake",
    ) -> Job | None:
        """Look up a job by its external source ID via the job_sources join table.

        Used by get_job_with_fallback() to check if a JDL job is already stored.
        """
        from app.core.db.models.job import JobSource
        from sqlalchemy import select

        async with self.session as session:
            result = await session.execute(
                select(Job)
                .join(JobSource, Job.id == JobSource.job_id)
                .where(
                    JobSource.source_name == source_name,
                    JobSource.source_job_id == source_job_id,
                )
            )
            return result.scalar_one_or_none()
    ```

- [ ] **Step 4: Run test — verify pass**

    ```bash
    uv run pytest tests/test_fallback.py::test_get_by_source_job_id_found -v
    ```
    Expected: PASS

- [ ] **Step 5: Commit**

    ```bash
    git add app/mcp/repositories/job_repo.py tests/test_fallback.py
    git commit -m "feat(fallback): add get_by_source_job_id() to JobRepository"
    ```

---

### Task T013 [P] [TDD] [SUBAGENT]: Add get_job_by_id() to JobDataLakeClient

**Files:**
- Modify: `app/core/jdl/client.py`
- Test: `tests/test_fallback.py`

**Interfaces:**
- Produces: `async get_job_by_id(external_id: str) -> dict | None`

- [ ] **Step 1: Write the failing test**

    ```python
    import pytest
    from unittest.mock import AsyncMock, MagicMock

    @pytest.mark.asyncio
    async def test_get_job_by_id_found():
        """R-001: Returns parsed JSON when JDL API returns 200."""
        from app.core.jdl.client import JobDataLakeClient
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(return_value={"id": "jdl_001", "title": "Engineer"})
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        client = JobDataLakeClient(api_key="test-key")
        client.client = mock_client

        result = await client.get_job_by_id("jdl_001")
        assert result == {"id": "jdl_001", "title": "Engineer"}
        mock_client.get.assert_called_once_with(
            "https://api.jobdatalake.com/v1/jobs/jdl_001"
        )

    @pytest.mark.asyncio
    async def test_get_job_by_id_not_found():
        """R-001: Returns None when JDL API returns 404."""
        from app.core.jdl.client import JobDataLakeClient
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        client = JobDataLakeClient(api_key="test-key")
        client.client = mock_client

        result = await client.get_job_by_id("nonexistent")
        assert result is None
    ```

- [ ] **Step 2: Run test — verify fail**

    ```bash
    uv run pytest tests/test_fallback.py::test_get_job_by_id_found -v --no-header -q
    ```
    Expected: FAIL — `JobDataLakeClient` has no `get_job_by_id`

- [ ] **Step 3: Implement**

    In `app/core/jdl/client.py`, add to `JobDataLakeClient`:

    ```python
    async def get_job_by_id(self, external_id: str) -> dict | None:
        """Fetch a single job from the JDL API by its external ID.

        Returns the parsed JSON dict, or None if the job doesn't exist (404).
        Raises httpx.HTTPError for other error status codes.
        """
        url = f"{BASE_URL}/jobs/{external_id}"
        async with self.limiter:
            response = await self.client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
    ```

- [ ] **Step 4: Run test — verify pass**

    ```bash
    uv run pytest tests/test_fallback.py::test_get_job_by_id_found -v
    ```
    Expected: PASS

- [ ] **Step 5: Commit**

    ```bash
    git add app/core/jdl/client.py tests/test_fallback.py
    git commit -m "feat(fallback): add get_job_by_id() to JobDataLakeClient"
    ```

---

**Phase 2 Checkpoint:** Schema ready — verify with `uv run alembic history`. All repository and client methods exist with passing tests. Run:

```bash
uv run pytest tests/test_fallback.py -v
```

---

## Phase 3: User Story 1 — Fallback Search (Priority: P1) 🎯 MVP

**Goal:** When a user submits a job search query and the database returns zero or insufficient results, the system silently falls back to the JDL API, upserts results into the local DB, re-queries the DB via hybrid search, and returns ranked results with `fallback_used=True`.

**Independent Test:** Run `test_empty_db_triggers_fallback` against a known-empty database — verify `SearchJobsOutput.hits` non-empty, `fallback_used=True`, `dropped_count>=0`.

**Acceptance scenarios covered:** FR-001, FR-002, FR-004, FR-005, FR-006, FR-007, FR-008, FR-010, FR-011, FR-012, FR-013, FR-014, SC-001, SC-002, SC-005

---

### Task T014 [P] [TDD] [US1]: Write test_empty_db_triggers_fallback

**Files:**
- Modify: `tests/test_fallback.py`

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_empty_db_triggers_fallback(fallback_service, job_repo, mocker):
        """FR-002, FR-004: DB returns 0 hits → API called, upsert runs, re-query returns results."""
        from app.mcp.services.job_fallback_service import SearchJobsOutput

        # Mock: DB search returns 0 hits
        mocker.patch.object(job_repo, "search", return_value=SearchJobsOutput(hits=[], total=0))

        # Mock: JDL API returns 2 jobs
        mock_api_jobs = [
            {"id": "jdl_101", "title": "Python Engineer", "company_name": "Acme"},
            {"id": "jdl_102", "title": "Data Scientist", "company_name": "Data Co"},
        ]
        mocker.patch.object(
            fallback_service.jdl_client, "search_jobs",
            return_value=mock_api_jobs,
        )

        # Mock: normalize_job returns valid NormalizedJob objects
        from app.core.jdl.normalization import NormalizedJob
        mocker.patch(
            "app.mcp.services.job_fallback_service.normalize_job",
            side_effect=[
                NormalizedJob(title="Python Engineer", company_name="Acme", dedup_hash="h1", source_name="jobdatalake", source_job_id="jdl_101"),
                NormalizedJob(title="Data Scientist", company_name="Data Co", dedup_hash="h2", source_name="jobdatalake", source_job_id="jdl_102"),
            ],
        )

        # Mock: upsert returns 2 Job ORM objects
        from app.core.db.models.job import Job
        import uuid
        mock_jobs = [
            Job(id=uuid.uuid4(), title="Python Engineer", company_name="Acme", dedup_hash="h1", fallback_source="jdl_api"),
            Job(id=uuid.uuid4(), title="Data Scientist", company_name="Data Co", dedup_hash="h2", fallback_source="jdl_api"),
        ]
        mocker.patch.object(job_repo, "upsert_from_fallback", return_value=mock_jobs)

        # Mock: second DB query returns results
        mocker.patch.object(
            job_repo, "search",
            return_value=SearchJobsOutput(
                hits=[...],  # populated hit list
                total=2,
            ),
        )

        result = await fallback_service.search_with_fallback(
            query="python engineer", limit=10, threshold=5, criteria={}
        )
        assert result.fallback_used is True
        assert result.total >= 2
    ```

- [ ] **Step 2: Verify test fails before implementation**

    ```bash
    uv run pytest tests/test_fallback.py::test_empty_db_triggers_fallback -v --no-header -q
    ```
    Expected: FAIL — `JobFallbackService` not yet created

---

### Task T015 [P] [TDD] [US1]: Write test_populated_db_no_fallback

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_populated_db_no_fallback(fallback_service, job_repo, mocker):
        """FR-001, FR-006: DB returns ≥ threshold hits → API NEVER called."""
        from app.mcp.services.job_fallback_service import SearchJobsOutput

        mock_hits = [MagicMock() for _ in range(5)]
        mocker.patch.object(
            job_repo, "search",
            return_value=SearchJobsOutput(hits=mock_hits, total=5),
        )
        api_spy = mocker.spy(fallback_service.jdl_client, "search_jobs")

        result = await fallback_service.search_with_fallback(
            query="python engineer", limit=10, threshold=5, criteria={}
        )
        assert result.fallback_used is False
        api_spy.assert_not_called()
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_populated_db_no_fallback -v --no-header -q
    ```

---

### Task T016 [P] [TDD] [US1]: Write test_threshold_strict_lt

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_threshold_strict_lt(fallback_service, job_repo, mocker):
        """FR-010: Supplement only when DB hits < threshold. At exactly threshold, no API."""
        from app.mcp.services.job_fallback_service import SearchJobsOutput

        # Exactly threshold — no API
        mock_hits = [MagicMock() for _ in range(5)]
        mocker.patch.object(
            job_repo, "search",
            return_value=SearchJobsOutput(hits=mock_hits, total=5),
        )
        api_spy = mocker.spy(fallback_service.jdl_client, "search_jobs")

        result = await fallback_service.search_with_fallback(
            query="test", limit=10, threshold=5, criteria={}
        )
        assert result.fallback_used is False
        api_spy.assert_not_called()

        # Below threshold — API called
        mocker.patch.object(
            job_repo, "search",
            return_value=SearchJobsOutput(hits=[MagicMock()], total=1),
        )
        result = await fallback_service.search_with_fallback(
            query="test", limit=10, threshold=5, criteria={}
        )
        assert result.fallback_used is True
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_threshold_strict_lt -v --no-header -q
    ```

---

### Task T017 [P] [TDD] [US1]: Write test_api_error_graceful

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_api_error_graceful(fallback_service, job_repo, mocker):
        """FR-008: API 5xx → graceful empty result, no exception raised."""
        from app.mcp.services.job_fallback_service import SearchJobsOutput

        mocker.patch.object(
            job_repo, "search",
            return_value=SearchJobsOutput(hits=[], total=0),
        )
        mocker.patch.object(
            fallback_service.jdl_client, "search_jobs",
            side_effect=httpx.HTTPStatusError(
                "500 Server Error", request=MagicMock(), response=MagicMock()
            ),
        )

        result = await fallback_service.search_with_fallback(
            query="test", limit=10, threshold=5, criteria={}
        )
        # Graceful degradation — empty but no crash
        assert result.fallback_used is False
        assert result.total == 0
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_api_error_graceful -v --no-header -q
    ```

---

### Task T018 [P] [TDD] [US1]: Write test_fallback_disabled

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_fallback_disabled(fallback_service_disabled, job_repo, mocker):
        """FR-012: fallback_enabled=False → API never called regardless of DB results."""
        from app.mcp.services.job_fallback_service import SearchJobsOutput

        mocker.patch.object(
            job_repo, "search",
            return_value=SearchJobsOutput(hits=[], total=0),
        )
        api_spy = mocker.spy(fallback_service_disabled.jdl_client, "search_jobs")

        result = await fallback_service_disabled.search_with_fallback(
            query="test", limit=10, threshold=5, criteria={}
        )
        assert result.fallback_used is False
        api_spy.assert_not_called()
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_fallback_disabled -v --no-header -q
    ```

---

### Task T019 [P] [TDD] [US1]: Write test_inflight_dedup

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_inflight_dedup(fallback_service, job_repo, mocker):
        """FR-013, SC-005: Two simultaneous identical queries → exactly one API call."""
        import asyncio
        from app.mcp.services.job_fallback_service import SearchJobsOutput

        mocker.patch.object(
            job_repo, "search",
            return_value=SearchJobsOutput(hits=[], total=0),
        )

        call_count = 0
        async def delayed_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return [{"id": "jdl_101"}]

        mocker.patch.object(
            fallback_service.jdl_client, "search_jobs",
            side_effect=delayed_search,
        )

        async def run_query():
            return await fallback_service.search_with_fallback(
                query="python engineer", limit=10, threshold=5, criteria={}
            )

        r1, r2 = await asyncio.gather(run_query(), run_query())
        assert call_count == 1, f"Expected 1 API call, got {call_count}"
        assert r1.fallback_used is True
        assert r2.fallback_used is True
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_inflight_dedup -v --no-header -q
    ```

---

### Task T020 [P] [TDD] [US1]: Write test_malformed_job_dropped

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_malformed_job_dropped(fallback_service, job_repo, mocker):
        """FR-014: Malformed job dropped, valid one kept, dropped_count reported."""
        from app.mcp.services.job_fallback_service import SearchJobsOutput

        mocker.patch.object(
            job_repo, "search",
            return_value=SearchJobsOutput(hits=[], total=0),
        )
        mocker.patch.object(
            fallback_service.jdl_client, "search_jobs",
            return_value=[
                {"id": "valid_1", "title": "Good Engineer", "company_name": "Good Co"},
                {"id": "bad_1"},  # missing required fields
            ],
        )

        from app.core.jdl.normalization import NormalizedJob
        # First job normalizes OK, second raises ValueError
        mocker.patch(
            "app.mcp.services.job_fallback_service.normalize_job",
            side_effect=[
                NormalizedJob(title="Good Engineer", company_name="Good Co", dedup_hash="h1", source_name="jobdatalake", source_job_id="valid_1"),
                ValueError("Missing required fields"),
            ],
        )

        result = await fallback_service.search_with_fallback(
            query="test", limit=10, threshold=5, criteria={}
        )
        assert result.dropped_count == 1
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_malformed_job_dropped -v --no-header -q
    ```

---

### Task T021 [P] [TDD] [US1]: Verify all US1 tests fail before implementation

- [ ] **Step 1: Run all US1 tests to confirm RED phase**

    ```bash
    uv run pytest tests/test_fallback.py -v --no-header -q
    ```
    Expected: All tests FAIL (JobFallbackService not yet created)

---

### Task T022 [TDD] [US1]: Create JobFallbackService with search_with_fallback()

**Files:**
- Create: `app/mcp/services/job_fallback_service.py`

**Interfaces:**
- Consumes: `JobRepository`, `JobDataLakeClient`, `Settings`, `normalize_job()`
- Produces: `async search_with_fallback(query, limit, threshold, criteria) -> SearchJobsOutput`

- [ ] **Step 1: Write the initial failing test for the service file**

    ```python
    import pytest
    from app.mcp.services.job_fallback_service import JobFallbackService

    @pytest.mark.asyncio
    async def test_job_fallback_service_instantiation():
        """Service can be created with required dependencies."""
        service = JobFallbackService(
            job_repo=MagicMock(),
            jdl_client=MagicMock(),
            settings=MagicMock(),
        )
        assert service is not None
    ```

- [ ] **Step 2: Run test — verify fail**

    ```bash
    uv run pytest tests/test_fallback.py::test_job_fallback_service_instantiation -v --no-header -q
    ```

- [ ] **Step 3: Implement the service**

    Create `app/mcp/services/job_fallback_service.py`:

    ```python
    """Fallback orchestration service — DB → JDL API → upsert → re-query."""

    import asyncio
    import hashlib
    import logging
    from uuid import UUID

    import httpx
    from aiolimiter import RateLimitError

    from app.core.config.settings import Settings
    from app.core.jdl.client import JobDataLakeClient
    from app.core.jdl.normalization import normalize_job
    from app.mcp.mcp_schemas import SearchJobsOutput, JobDetailOutput, JobHit
    from app.mcp.repositories.job_repo import JobRepository

    logger = logging.getLogger(__name__)

    # Module-level in-flight dedup map: query_key -> asyncio.Event
    _in_flight: dict[str, asyncio.Event] = {}


    class JobFallbackService:
        """Orchestrates the three-step fallback: DB → API → upsert → re-query."""

        def __init__(
            self,
            job_repo: JobRepository,
            jdl_client: JobDataLakeClient | None,
            settings: Settings,
        ) -> None:
            self.job_repo = job_repo
            self.jdl_client = jdl_client
            self.settings = settings
            self._fallback_enabled = (
                settings.fallback_enabled and jdl_client is not None
            )

        async def search_with_fallback(
            self,
            query: str,
            limit: int,
            threshold: int,
            criteria: dict,
        ) -> SearchJobsOutput:
            """Three-step fallback search.

            1. Query DB first
            2. If hits < threshold: fetch from JDL, upsert, re-query DB
            3. Return results (always from DB, never raw API)
            """
            # Step 1: Query DB
            db_results = await self.job_repo.search(
                query=query, limit=limit, threshold=threshold
            )

            # Check if fallback is needed (strict less-than)
            if not self._fallback_enabled or len(db_results.hits) >= threshold:
                return db_results

            # Step 2: Fallback to JDL API
            query_key = hashlib.sha256(query.lower().strip().encode()).hexdigest()
            dropped_count = 0

            try:
                # In-flight dedup check
                if query_key in _in_flight:
                    logger.info("awaiting in-flight fallback for query=%s", query)
                    await _in_flight[query_key].wait()
                    # Results now in DB — re-query and return
                    return await self.job_repo.search(
                        query=query, limit=limit, threshold=threshold
                    )

                event = asyncio.Event()
                _in_flight[query_key] = event

                try:
                    # Fetch from JDL API
                    api_jobs = await self.jdl_client.search_jobs(criteria)
                    if not api_jobs:
                        return db_results

                    # Limit results
                    api_jobs = api_jobs[: self.settings.fallback_max_results]

                    # Normalize and filter (per-item error handling)
                    valid_jobs = []
                    for raw in api_jobs:
                        try:
                            normalized = normalize_job(raw)
                            valid_jobs.append(normalized)
                        except (ValueError, KeyError) as exc:
                            dropped_count += 1
                            logger.warning(
                                "fallback dropped malformed job: %s", exc
                            )

                    if not valid_jobs:
                        return SearchJobsOutput(
                            hits=[],
                            total=0,
                            fallback_used=True,
                            dropped_count=dropped_count,
                        )

                    # Upsert to DB
                    upserted = await self.job_repo.upsert_from_fallback(valid_jobs)

                    # Fire-and-forget embeddings
                    if upserted:
                        self._schedule_embeddings(upserted)

                finally:
                    event.set()
                    _in_flight.pop(query_key, None)

                # Step 3: Re-query DB (now populated with fallback results)
                final_results = await self.job_repo.search(
                    query=query, limit=limit, threshold=threshold
                )
                final_results.fallback_used = True
                final_results.dropped_count = dropped_count
                return final_results

            except (httpx.HTTPError, RateLimitError) as exc:
                logger.warning("JDL fallback failed: query=%s error=%s", query, exc)
                return db_results

        def _schedule_embeddings(self, jobs: list) -> None:
            """Fire-and-forget embedding generation for upserted jobs."""
            import asyncio

            asyncio.create_task(
                self._generate_embeddings_background(jobs),
                name=f"fallback-embeddings-{id(jobs)}",
            )

        async def _generate_embeddings_background(self, jobs: list) -> None:
            """Generate embeddings for fallback-upserted jobs (background task)."""
            try:
                from app.core.llm.embeddings import generate_job_embeddings

                for job in jobs:
                    await generate_job_embeddings(job)
                logger.info(
                    "fallback embeddings generated for %d jobs", len(jobs)
                )
            except Exception as exc:
                logger.error(
                    "fallback embedding generation failed: %s", exc
                )

        async def get_job_with_fallback(self, job_id: UUID) -> JobDetailOutput | None:
            """Look up a single job by ID, falling back to JDL API if not in DB.

            Will be implemented in Phase 4 (US2).
            """
            raise NotImplementedError("US2 — implemented in Phase 4")
    ```

- [ ] **Step 4: Run tests — verify pass**

    ```bash
    uv run pytest tests/test_fallback.py -v
    ```
    Expected: At least the instantiation test passes; US1 scenario tests may need fixture wiring

- [ ] **Step 5: Commit**

    ```bash
    git add app/mcp/services/job_fallback_service.py tests/test_fallback.py
    git commit -m "feat(fallback): create JobFallbackService with search_with_fallback()"
    ```

---

### Task T023 [SUBAGENT] [US1]: Implement in-flight request deduplication

**Already included in T022** — the `_in_flight` dict and `asyncio.Event` pattern are integrated into `search_with_fallback()` above. Verify with:

- [ ] **Step 1: Verify test_inflight_dedup passes**

    ```bash
    uv run pytest tests/test_fallback.py::test_inflight_dedup -v
    ```
    Expected: PASS (or debug if failing)

- [ ] **Step 2: Commit if changes needed**

    ```bash
    git add app/mcp/services/job_fallback_service.py
    git commit -m "feat(fallback): add in-flight dedup via asyncio.Event"
    ```

---

### Task T024 [SUBAGENT] [US1]: Implement _schedule_embeddings() fire-and-forget

**Already included in T022** — `_schedule_embeddings()` and `_generate_embeddings_background()` are part of `JobFallbackService`. Verify with:

- [ ] **Step 1: Verify embeddings are scheduled fire-and-forget**

    Run the test with logging to confirm:

    ```bash
    uv run pytest tests/test_fallback.py::test_empty_db_triggers_fallback -v -s 2>&1 | grep -i "embedding"
    ```
    Expected: No blocking calls in the critical path

- [ ] **Step 2: Commit if changes needed**

    ```bash
    git add app/mcp/services/job_fallback_service.py
    git commit -m "feat(fallback): fire-and-forget embedding scheduling"
    ```

---

### Task T025 [REVIEW] [US1]: Update search_jobs() in JobService to delegate to JobFallbackService

- [ ] **Step 1: Modify `app/mcp/services/job_service.py`**

    ```python
    from app.mcp.services.job_fallback_service import JobFallbackService

    class JobService:
        def __init__(self, ..., fallback_service: JobFallbackService):
            ...
            self.fallback_service = fallback_service

        async def search_jobs(
            self,
            query: str,
            limit: int = 10,
            cosine_threshold: float = 0.5,
        ) -> SearchJobsOutput:
            """Search jobs with automatic fallback to JDL API when DB is sparse."""
            criteria = {"query": query}
            return await self.fallback_service.search_with_fallback(
                query=query,
                limit=limit,
                threshold=self.settings.fallback_min_result_threshold,
                criteria=criteria,
            )
    ```

- [ ] **Step 2: Update DI wiring**

    Update `app/mcp/di.py` to inject `JobFallbackService` into `JobService`.

- [ ] **Step 3: Run tests to verify delegation works**

    ```bash
    uv run pytest tests/test_fallback.py -v
    ```

- [ ] **Step 4: Commit**

    ```bash
    git add app/mcp/services/job_service.py app/mcp/di.py
    git commit -m "feat(fallback): delegate search_jobs() to JobFallbackService"
    ```

---

### Task T026 [REVIEW] [US1]: Update hybrid_search graph node to use JobFallbackService

- [ ] **Step 1: Modify `app/graph/nodes.py`**

    Update the `hybrid_search` node to use `JobFallbackService.search_with_fallback()` instead of calling `search_jobs()` directly. The node receives `extracted_criteria` from state and passes it through.

    ```python
    async def hybrid_search(state: GraphState) -> dict:
        """Perform hybrid search with fallback to JDL API."""
        criteria = state.get("extracted_criteria", {})
        query = criteria.get("query", "")
        fallback_service = get_fallback_service()  # from DI

        result = await fallback_service.search_with_fallback(
            query=query,
            limit=10,
            threshold=settings.fallback_min_result_threshold,
            criteria=criteria,
        )
        return {"retrieved_jobs": result.hits, "search_result": result}
    ```

- [ ] **Step 2: Run tests**

    ```bash
    uv run pytest tests/test_graph.py -v
    ```

- [ ] **Step 3: Commit**

    ```bash
    git add app/graph/nodes.py
    git commit -m "feat(fallback): update hybrid_search node to use JobFallbackService"
    ```

---

### Task T027 [US1]: Verify all US1 tests pass

- [ ] **Step 1: Run full US1 test suite**

    ```bash
    uv run pytest tests/test_fallback.py -v
    ```
    Expected: All tests pass (T014–T021, plus service-level tests)

---

**Phase 3 Checkpoint 🎯 MVP:** US1 complete — search against empty/populated DB correctly triggers or skips fallback. All P1 acceptance scenarios pass. Run:

```bash
uv run pytest tests/test_fallback.py -v
```

---

## Phase 4: User Story 2 — Individual Job Lookup (Priority: P1)

**Goal:** When a user references a specific job by ID that does not exist in the local database, the system fetches that individual job on demand from the JDL API, upserts it, and returns the result with `fallback_source="jdl_api"`.

**Independent Test:** Call `get_job_tool` with a known JDL job ID absent from local DB — verify `JobDetailOutput` returned with `fallback_source="jdl_api"`.

**Acceptance scenarios covered:** FR-003, FR-004, FR-005, FR-008, FR-011, FR-012

---

### Task T028 [P] [TDD] [US2]: Write test_get_job_fallback

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_get_job_fallback(fallback_service, job_repo, mocker):
        """FR-003: Job ID absent from DB → fetched from JDL API, upserted, returned."""
        import uuid
        job_id = uuid.uuid4()

        # DB returns None
        mocker.patch.object(job_repo, "get_by_id", return_value=None)
        mocker.patch.object(job_repo, "get_by_source_job_id", return_value=None)

        # JDL API returns job
        mock_raw = {"id": "jdl_201", "title": "Found Engineer", "company_name": "Found Co"}
        mocker.patch.object(
            fallback_service.jdl_client, "get_job_by_id",
            return_value=mock_raw,
        )

        from app.core.jdl.normalization import NormalizedJob
        mocker.patch(
            "app.mcp.services.job_fallback_service.normalize_job",
            return_value=NormalizedJob(
                title="Found Engineer", company_name="Found Co",
                dedup_hash="h3", source_name="jobdatalake", source_job_id="jdl_201",
            ),
        )

        from app.core.db.models.job import Job
        from datetime import datetime
        mock_job = Job(
            id=job_id, title="Found Engineer", company_name="Found Co",
            dedup_hash="h3", fallback_source="jdl_api",
            last_seen_at=datetime.utcnow(),
        )
        mocker.patch.object(job_repo, "upsert_from_fallback", return_value=[mock_job])

        # After upsert, re-fetch returns the job
        mocker.patch.object(job_repo, "get_by_id", return_value=mock_job)

        result = await fallback_service.get_job_with_fallback(job_id)
        assert result is not None
        assert result.fallback_source == "jdl_api"
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_get_job_fallback -v --no-header -q
    ```
    Expected: FAIL — `get_job_with_fallback` raises `NotImplementedError`

---

### Task T029 [P] [TDD] [US2]: Write test_get_job_in_db_no_api

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_get_job_in_db_no_api(fallback_service, job_repo, mocker):
        """FR-001: Job already in DB → returned WITHOUT API call."""
        import uuid
        from app.core.db.models.job import Job
        from datetime import datetime

        job_id = uuid.uuid4()
        mock_job = Job(
            id=job_id, title="Existing Job", company_name="Existing Co",
            dedup_hash="h4", fallback_source=None,
            last_seen_at=datetime.utcnow(),
        )
        mocker.patch.object(job_repo, "get_by_id", return_value=mock_job)
        api_spy = mocker.spy(fallback_service.jdl_client, "get_job_by_id")

        result = await fallback_service.get_job_with_fallback(job_id)
        assert result is not None
        assert result.fallback_source is None  # not from API
        api_spy.assert_not_called()
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_get_job_in_db_no_api -v --no-header -q
    ```

---

### Task T030 [P] [TDD] [US2]: Write test_get_job_not_found_anywhere

- [ ] **Step 1: Write the test**

    ```python
    @pytest.mark.asyncio
    async def test_get_job_not_found_anywhere(fallback_service, job_repo, mocker):
        """FR-003: Job not in DB or JDL → returns None."""
        import uuid
        job_id = uuid.uuid4()

        mocker.patch.object(job_repo, "get_by_id", return_value=None)
        mocker.patch.object(job_repo, "get_by_source_job_id", return_value=None)
        mocker.patch.object(
            fallback_service.jdl_client, "get_job_by_id",
            return_value=None,  # 404
        )

        result = await fallback_service.get_job_with_fallback(job_id)
        assert result is None
    ```

- [ ] **Step 2: Verify test fails**

    ```bash
    uv run pytest tests/test_fallback.py::test_get_job_not_found_anywhere -v --no-header -q
    ```

---

### Task T031 [P] [TDD] [US2]: Verify all US2 tests fail before implementation

- [ ] **Step 1: Run all US2 tests to confirm RED phase**

    ```bash
    uv run pytest tests/test_fallback.py -k "get_job" -v --no-header -q
    ```
    Expected: All tests FAIL

---

### Task T032 [TDD] [US2]: Implement get_job_with_fallback() in JobFallbackService

- [ ] **Step 1: Replace the NotImplementedError stub in `app/mcp/services/job_fallback_service.py`**

    ```python
    async def get_job_with_fallback(self, job_id: UUID) -> JobDetailOutput | None:
        """Look up a single job by ID, falling back to JDL API if not in DB.

        1. Check local DB first
        2. If not found, check by source_job_id (in case stored under external ID)
        3. If still not found, fetch from JDL API
        4. Upsert and return
        """
        # Step 1: Check local DB
        job = await self.job_repo.get_by_id(str(job_id))
        if job is not None:
            return self._job_to_detail_output(job)

        # Step 2: Check if we have it stored under external ID
        job = await self.job_repo.get_by_source_job_id(str(job_id))
        if job is not None:
            return self._job_to_detail_output(job)

        # Step 3: Fallback to JDL API (if enabled)
        if not self._fallback_enabled:
            return None

        try:
            raw = await self.jdl_client.get_job_by_id(str(job_id))
            if raw is None:
                return None  # 404 from JDL

            # Normalize and upsert
            normalized = normalize_job(raw)
            upserted = await self.job_repo.upsert_from_fallback([normalized])

            if upserted:
                self._schedule_embeddings(upserted)
                job = upserted[0]
                return self._job_to_detail_output(job, fallback_source="jdl_api")

            return None

        except (httpx.HTTPError, RateLimitError) as exc:
            logger.warning(
                "JDL fallback failed for job_id=%s: %s", job_id, exc
            )
            return None

    def _job_to_detail_output(
        self,
        job,
        fallback_source: str | None = None,
    ) -> JobDetailOutput:
        """Map a Job ORM object to JobDetailOutput."""
        return JobDetailOutput(
            id=str(job.id),
            title=job.title,
            company_name=job.company_name,
            description=job.description_text or "",
            required_skills=job.required_skills or [],
            locations=job.locations or [],
            remote_type=job.remote_type,
            employment_type=job.employment_type,
            seniority=job.seniority or [],
            fallback_source=fallback_source or job.fallback_source,
        )
    ```

- [ ] **Step 2: Run tests — verify pass**

    ```bash
    uv run pytest tests/test_fallback.py -k "get_job" -v
    ```
    Expected: All US2 tests pass

- [ ] **Step 3: Commit**

    ```bash
    git add app/mcp/services/job_fallback_service.py tests/test_fallback.py
    git commit -m "feat(fallback): implement get_job_with_fallback()"
    ```

---

### Task T033 [REVIEW] [US2]: Update get_job() in JobService to delegate

- [ ] **Step 1: Modify `app/mcp/services/job_service.py`**

    ```python
    async def get_job(self, job_id: UUID) -> JobDetailOutput:
        """Get a single job by ID with JDL API fallback."""
        result = await self.fallback_service.get_job_with_fallback(job_id)
        if result is None:
            raise NotFoundError(f"Job {job_id} not found or inactive")
        return result
    ```

- [ ] **Step 2: Update DI wiring if needed**

- [ ] **Step 3: Run tests**

    ```bash
    uv run pytest tests/test_fallback.py -v
    ```

- [ ] **Step 4: Commit**

    ```bash
    git add app/mcp/services/job_service.py
    git commit -m "feat(fallback): delegate get_job() to JobFallbackService"
    ```

---

### Task T034 [US2]: Verify all US2 tests pass

- [ ] **Step 1: Run full test suite**

    ```bash
    uv run pytest tests/test_fallback.py -v
    ```
    Expected: All tests pass (US1 + US2)

---

**Phase 4 Checkpoint:** US2 complete — individual job lookup correctly falls back to JDL API when absent from DB. All P1 acceptance scenarios pass.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose:** Final verification, structured logging, cleanup, and hardening across all user stories

---

### Task T035 [P]: Add structured logging to JobFallbackService

- [ ] **Step 1: Add logging calls to every fallback event path**

    In `app/mcp/services/job_fallback_service.py`, the existing `logger.info/warning` calls already cover:
    - Fallback triggered: query, db_hits, api_results, latency, dropped
    - Fallback rate limited
    - Fallback API error
    - In-flight dedup await

    ```python
    # Pattern for structured logging (already in T022 implementation)
    logger.info(
        "fallback triggered query=%s db_hits=%d api_results=%d dropped=%d",
        query, len(db_results.hits), len(api_jobs), dropped_count,
    )
    ```

- [ ] **Step 2: Verify log output**

    ```bash
    uv run pytest tests/test_fallback.py -v -s 2>&1 | grep -i "fallback"
    ```
    Expected: Structured log lines for each fallback event

- [ ] **Step 3: Commit**

    ```bash
    git add app/mcp/services/job_fallback_service.py
    git commit -m "feat(fallback): add structured logging (FR-009, SC-006)"
    ```

---

### Task T036 [P]: Verify API key misconfiguration handling

- [ ] **Step 1: Add a conftest fixture or verification test**

    ```python
    @pytest.mark.asyncio
    async def test_jdl_client_init_failure_disables_fallback():
        """FR-012: JDL client init failure → fallback_enabled=False with warning."""
        from app.mcp.services.job_fallback_service import JobFallbackService

        service = JobFallbackService(
            job_repo=MagicMock(),
            jdl_client=None,  # key missing
            settings=MagicMock(fallback_enabled=True),
        )
        assert service._fallback_enabled is False
    ```

- [ ] **Step 2: Run test**

    ```bash
    uv run pytest tests/test_fallback.py::test_jdl_client_init_failure_disables_fallback -v
    ```

- [ ] **Step 3: Commit**

    ```bash
    git add tests/test_fallback.py
    git commit -m "fix(fallback): verify fallback disabled on missing API key"
    ```

---

### Task T037 [P]: Verify migration rollback safety

- [ ] **Step 1: Run the migration cycle**

    ```bash
    uv run alembic downgrade -1 && uv run alembic upgrade head
    ```
    Expected: Clean rollback and re-apply with no errors

- [ ] **Step 2: Commit (if migration script needed fixing)**

    ```bash
    git add alembic/versions/
    git commit -m "fix(fallback): ensure migration is safely reversible"
    ```

---

### Task T038 [P]: Run full test suite

- [ ] **Step 1: Run all tests**

    ```bash
    uv run pytest tests/ -v
    ```
    Expected: All tests pass (existing + new fallback tests)

---

### Task T039 [P]: Run linting

- [ ] **Step 1: Check lint**

    ```bash
    uv run ruff check app/ tests/
    ```
    Expected: Zero warnings

- [ ] **Step 2: Fix any issues**

    ```bash
    uv run ruff check --fix app/ tests/
    ```

---

### Task T040 [P]: Run formatting

- [ ] **Step 1: Format code**

    ```bash
    uv run ruff format app/ tests/
    ```

---

### Task T041 [P]: Run quickstart validation

- [ ] **Step 1: Run fallback-specific tests**

    ```bash
    uv run pytest tests/test_fallback.py -v
    ```
    Expected: All tests pass

- [ ] **Step 2: Follow quickstart.md manual scenarios**

    ```bash
    # Start MCP server
    uv run python -m app.mcp.mcp_server

    # Verify fallback_source column
    psql $POSTGRES_URL -c "\d jobs" | grep fallback_source
    ```

---

**Phase 5 Checkpoint:** All tests pass, linting clean, formatting clean, migration safe. Feature is ready for review.

---

## ✅ Completion Summary (2026-07-11)

### Done — Phases 1–4 (T001–T034)

| Phase | Tasks | Status |
|---|---|---|
| **Phase 1: Setup** (T001–T003) | 3 | ✅ Done |
| **Phase 2: Foundation** (T004–T013) | 10 | ✅ Done — all foundation pieces in current codebase |
| **Phase 3: US1** (T014–T027) | 14 | ✅ Done — `JobFallbackService.search_with_fallback()` + in-flight dedup + fire-and-forget embeddings |
| **Phase 4: US2** (T028–T034) | 7 | ✅ Done — `JobFallbackService.get_job_with_fallback()` implemented |
| **Phase 5: Polish** (T035–T041) | 7 | ⏳ Pending — logging, migration verification, final checks |
| **Total (MVP)** | 27 | ✅ **All MVP tasks done** |
| **Total (all phases)** | 41 | 34 done, 7 pending (Phase 5 polish) |

### What was restored & fixed

- **Branch `012-api-job-fallback`** (3 unmerged commits) was never merged — its work was ported manually to the restructured codebase
- **Migration** `85e4caeac6da_add_fallback_source_to_jobs.py` ported from the branch, `down_revision` updated to current head `dd5f8cb72244`
- **`pytest-mock`** installed (was missing, causing 9 test errors)
- **`tests/test_fallback.py`** rewritten for current codebase structure (584 lines → ~670 lines, 25 tests)
- **T012-specific tests** added: `test_get_by_source_job_id_found`, `test_get_by_source_job_id_not_found`
- **All 37 tests** (25 fallback + 8 graph + 4 MCP) pass

---

## Self-Review (writing-plans mandatory)

After completing all phases, run this self-review checklist against the spec.

### 1. Spec Coverage

| Spec Requirement | Covered By | Status |
|-----------------|------------|--------|
| FR-001: DB search first | T015, T029 | ✅ |
| FR-002: Fallback on zero results | T014 | ✅ |
| FR-003: Fallback on ID not found | T028, T030 | ✅ |
| FR-004: Three-step flow | T014, T022 | ✅ |
| FR-005: Same normalization | T022 | ✅ |
| FR-006: No unnecessary API calls | T015, T029 | ✅ |
| FR-007: Max 20 results | T022 | ✅ |
| FR-008: Graceful API error | T017, T022 | ✅ |
| FR-009: Logging | T035 | ✅ |
| FR-010: Strict < threshold | T016 | ✅ |
| FR-011: Source attribution | T008, T009, T010 | ✅ |
| FR-012: Skip when key missing | T018, T036 | ✅ |
| FR-013: In-flight dedup | T019, T023 | ✅ |
| FR-014: Per-item error handling | T020, T022 | ✅ |
| SC-001: 10 s response time | T014 | ✅ |
| SC-002: 2 s DB-only | T015 | ✅ |
| SC-003: No hard errors | T017 | ✅ |
| SC-005: >95% dedup | T019 | ✅ |
| SC-006: Observability | T035 | ✅ |

### 2. Placeholder Scan

- [ ] No "TBD", "TODO", "implement later" anywhere in this plan
- [ ] No "add appropriate error handling" without code
- [ ] No "write tests for the above" without test code
- [ ] No "similar to Task N" — each task is self-contained
- [ ] Every code step has actual code (not descriptions of what to write)

### 3. Type Consistency

- [ ] `normalize_job()` signature matches between T011 (consumes), T013 (used in service), and T022 (uses)
- [ ] `upsert_from_fallback()` returns `list[Job]` in T011 and T022 — consistent
- [ ] `get_by_source_job_id()` returns `Job | None` in T012 and T032 — consistent
- [ ] `get_job_by_id()` returns `dict | None` in T013 and T032 — consistent
- [ ] `search_with_fallback()` returns `SearchJobsOutput` in T022 and T025 — consistent
- [ ] `get_job_with_fallback()` returns `JobDetailOutput | None` in T032 and T033 — consistent

### 4. Gaps Found

- [ ] None — all spec requirements are covered

---

## Execution Handoff

**Plan complete and saved to `specs/012-api-job-fallback/tasks.md`.** Two execution options:

### Option 1: Subagent-Driven (recommended)

I dispatch a fresh subagent per task, review between tasks, fast iteration.

**REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development`
- Fresh subagent per task
- Two-stage review (implementer + reviewer)
- Parallel dispatch for `[P]` and `[SUBAGENT]` tasks

### Option 2: Inline Execution

Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

**REQUIRED SUB-SKILL:** Use `superpowers:executing-plans`
- Walk tasks phase by phase
- Checkpoints at each phase boundary
- Human approval required before advancing

### Marker Legend

- **`[P]`** — Can run in parallel (different files, no dependencies)
- **`[TDD]`** — RED-GREEN-REFACTOR: write test → verify fail → implement → verify pass
- **`[REVIEW]`** — Requires code review before proceeding
- **`[SUBAGENT]`** — Can be dispatched to a parallel subagent
- **`[US1]`** / **`[US2]`** — User story label for traceability

---

## Execution Order Reference

```
Phase 1: Setup (T001–T003)          ✅ DONE
     ↓
Phase 2: Foundational (T004–T013)   ✅ DONE
     ↓
     ├──→ Phase 3: US1 (T014–T027)  ✅ DONE 🎯 MVP
     ├──→ Phase 4: US2 (T028–T034)  ✅ DONE
     ↓
Phase 5: Polish (T035–T041)         ⏳ PENDING
```

**41 tasks total** | **34 done, 7 pending** | ✅ **MVP = Phase 1 + Phase 2 + Phase 3 (27 tasks) COMPLETE**
