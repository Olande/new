"""Tests for API Job Fallback feature (spec 012-api-job-fallback).

Test layout matches the spec's test matrix.
Every test follows RED-GREEN-REFACTOR: written first, verified failing,
then implementation makes them pass.

Runs entirely from process-level mocks — no database required.
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_mock  # noqa: F401 — provides the 'mocker' fixture

from app.core.config.settings import Settings
from app.mcp.mcp_schemas import JobDetailOutput, JobHit, SearchJobsOutput

# =========================================================================
# T004: Fallback config defaults
# =========================================================================


def test_fallback_settings_defaults():
    """FR-010, FR-012: Fallback settings have correct defaults."""
    settings = Settings()
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


# =========================================================================
# T005: Job model has fallback_source column
# =========================================================================


def test_job_model_has_fallback_source():
    """FR-011: Job model supports fallback_source column."""
    import uuid

    from app.core.db.models.job import Job

    job = Job(
        id=uuid.uuid4(),
        title="Test Engineer",
        dedup_hash="test_hash_001",
        company_name="Acme",
        fallback_source="jdl_api",
    )
    assert job.fallback_source == "jdl_api"


def test_job_model_fallback_source_nullable():
    """Existing jobs have fallback_source=NULL (backward compat)."""
    import uuid

    from app.core.db.models.job import Job

    job = Job(
        id=uuid.uuid4(),
        title="Test Engineer",
        dedup_hash="test_hash_002",
        company_name="Acme",
    )
    assert job.fallback_source is None


# =========================================================================
# T008: JobHit carries fallback_source
# =========================================================================

_JOB_HIT_KWARGS = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Engineer",
    "company_name": "Acme",
    "score": 0.95,
}


def test_job_hit_has_fallback_source():
    """FR-011: JobHit carries fallback_source attribution."""
    hit = JobHit(**_JOB_HIT_KWARGS, fallback_source="jdl_api")
    assert hit.fallback_source == "jdl_api"


def test_job_hit_fallback_source_default_none():
    """Backward compat: fallback_source defaults to None."""
    hit = JobHit(**_JOB_HIT_KWARGS)
    assert hit.fallback_source is None


# =========================================================================
# T009: SearchJobsOutput carries fallback_used and dropped_count
# =========================================================================


def test_search_jobs_output_fallback_fields():
    """FR-011, FR-014: Output carries fallback_used and dropped_count."""
    result = SearchJobsOutput(hits=[], total=0, fallback_used=True, dropped_count=2)
    assert result.fallback_used is True
    assert result.dropped_count == 2


def test_search_jobs_output_defaults():
    """Backward compat: new fields default to False/0."""
    result = SearchJobsOutput(hits=[], total=0)
    assert result.fallback_used is False
    assert result.dropped_count == 0


# =========================================================================
# T010: JobDetailOutput carries fallback_source
# =========================================================================


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
        id="550e8400-e29b-41d4-a716-446655440000",
        title="Engineer",
        company_name="Acme",
    )
    assert detail.fallback_source is None


# =========================================================================
# T012: get_by_source_job_id() in JobRepository
# =========================================================================


@pytest.mark.asyncio
async def test_get_by_source_job_id_found():
    """Returns Job when source_job_id matches."""
    from app.mcp.repositories.job_repo import JobRepository

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_job = MagicMock()
    mock_job.title = "Sample Job"
    mock_result.scalar_one_or_none.return_value = mock_job
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = JobRepository(session=mock_session)
    job = await repo.get_by_source_job_id("jdl_source_001")
    assert job is not None
    assert job.title == "Sample Job"


@pytest.mark.asyncio
async def test_get_by_source_job_id_not_found():
    """Returns None when source_job_id doesn't exist."""
    from app.mcp.repositories.job_repo import JobRepository

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = JobRepository(session=mock_session)
    job = await repo.get_by_source_job_id("nonexistent")
    assert job is None


# =========================================================================
# T011: upsert_from_fallback() in JobRepository
# =========================================================================


@pytest.mark.asyncio
async def test_upsert_from_fallback_empty():
    """Empty input returns empty list."""
    from app.mcp.repositories.job_repo import JobRepository

    repo = JobRepository(session=MagicMock())
    result = await repo.upsert_from_fallback([])
    assert result == []


# =========================================================================
# T013: JobDataLakeClient.get_job_by_id()
# =========================================================================


@pytest.mark.asyncio
async def test_get_job_by_id_found():
    """R-001: Returns parsed JSON when JDL API returns 200."""
    from app.core.jdl.client import JobDataLakeClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "jdl_001", "title": "Engineer"}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client = JobDataLakeClient(api_key="test-key")
    client.client = mock_client
    # bypass rate limiter for test
    client.limiter = MagicMock()
    client.limiter.__aenter__ = AsyncMock(return_value=None)
    client.limiter.__aexit__ = AsyncMock(return_value=None)

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
    client.limiter = MagicMock()
    client.limiter.__aenter__ = AsyncMock(return_value=None)
    client.limiter.__aexit__ = AsyncMock(return_value=None)

    result = await client.get_job_by_id("nonexistent")
    assert result is None


# =========================================================================
# T022: JobFallbackService instantiation
# =========================================================================


def test_job_fallback_service_instantiation():
    """Service can be created with required dependencies."""
    from app.mcp.services.job_fallback_service import JobFallbackService

    service = JobFallbackService(
        job_repo=MagicMock(),
        jdl_client=MagicMock(),
        settings=MagicMock(fallback_enabled=True),
    )
    assert service is not None


# =========================================================================
# Fixtures for service-level tests
# =========================================================================


@pytest.fixture
def mock_settings():
    s = MagicMock(spec=Settings)
    s.fallback_enabled = True
    s.fallback_min_result_threshold = 5
    s.fallback_max_results = 20
    return s


@pytest.fixture
def job_repo():
    return MagicMock()


@pytest.fixture
def mock_jdl_client():
    return MagicMock()


@pytest.fixture
def fallback_service(job_repo, mock_jdl_client, mock_settings):
    from app.mcp.services.job_fallback_service import JobFallbackService

    return JobFallbackService(
        job_repo=job_repo,
        jdl_client=mock_jdl_client,
        settings=mock_settings,
    )


@pytest.fixture
def fallback_service_disabled(job_repo, mock_jdl_client, mock_settings):
    from app.mcp.services.job_fallback_service import JobFallbackService

    mock_settings.fallback_enabled = False
    return JobFallbackService(
        job_repo=job_repo,
        jdl_client=mock_jdl_client,
        settings=mock_settings,
    )


# =========================================================================
# T014-T016: US1 search_with_fallback() scenario tests
# =========================================================================


@pytest.mark.asyncio
async def test_empty_db_triggers_fallback(fallback_service, job_repo, mocker):
    """FR-002, FR-004: DB returns 0 hits -> API called, upsert runs, re-query returns results."""
    import uuid

    from app.core.db.models.job import Job

    # DB search returns empty list
    job_repo.search = AsyncMock(return_value=[])

    # JDL API returns raw jobs
    mock_api_response = {
        "jobs": [
            {
                "id": "jdl_101",
                "title": "Python Engineer",
                "company_name": "Acme",
                "dedup_hash": "h1",
            },
            {
                "id": "jdl_102",
                "title": "Data Scientist",
                "company_name": "Data Co",
                "dedup_hash": "h2",
            },
        ]
    }
    fallback_service.jdl_client.search_jobs = AsyncMock(return_value=mock_api_response)

    # Mock normalize_job to return valid JobCreate objects
    from datetime import datetime

    from app.core.jdl.schemas import JobCreate, JobSourceCreate

    def make_job_create(title, company, dedup):
        return JobCreate(
            title=title,
            company_name=company,
            dedup_hash=dedup,
            required_skills=[],
            locations=[],
            countries=[],
            seniority=[],
            status="active",
            source=JobSourceCreate(
                source_name="jobdatalake",
                source_job_id="jdl_001",
                source_url="https://example.com",
                first_seen_at=datetime.now(),
            ),
        )

    mocker.patch(
        "app.mcp.services.job_fallback_service.normalize_job",
        side_effect=[
            make_job_create("Python Engineer", "Acme", "h1"),
            make_job_create("Data Scientist", "Data Co", "h2"),
        ],
    )

    # Upsert returns mock Job objects
    mock_jobs = [
        Job(
            id=uuid.uuid4(),
            title="Python Engineer",
            company_name="Acme",
            dedup_hash="h1",
            fallback_source="jdl_api",
        ),
        Job(
            id=uuid.uuid4(),
            title="Data Scientist",
            company_name="Data Co",
            dedup_hash="h2",
            fallback_source="jdl_api",
        ),
    ]
    job_repo.upsert_from_fallback = AsyncMock(return_value=mock_jobs)

    # Second DB query (after upsert) returns populated results
    job_repo.search = AsyncMock(side_effect=[[], mock_jobs])

    # Suppress fire-and-forget embeddings
    mocker.patch.object(fallback_service, "_schedule_embeddings")

    result = await fallback_service.search_with_fallback(
        query="python engineer", limit=10, threshold=5, criteria={}
    )
    assert result.fallback_used is True
    assert result.total >= 2


@pytest.mark.asyncio
async def test_populated_db_no_fallback(fallback_service, job_repo, mocker):
    """FR-001, FR-006: DB returns >= threshold hits -> API NEVER called."""
    import uuid

    from app.core.db.models.job import Job

    mock_jobs = [
        Job(
            id=uuid.uuid4(),
            title=f"Job {i}",
            company_name="Acme",
            dedup_hash=f"h{i}",
        )
        for i in range(5)
    ]
    job_repo.search = AsyncMock(return_value=mock_jobs)
    api_spy = mocker.patch.object(fallback_service.jdl_client, "search_jobs")

    result = await fallback_service.search_with_fallback(
        query="python engineer", limit=10, threshold=5, criteria={}
    )
    assert result.fallback_used is False
    api_spy.assert_not_called()


@pytest.mark.asyncio
async def test_threshold_strict_lt(fallback_service, job_repo, mocker):
    """FR-010: Supplement only when DB hits < threshold. At exactly threshold, no API."""
    import uuid

    from app.core.db.models.job import Job

    # Exactly at threshold (5 hits) -- no API
    five_jobs = [
        Job(
            id=uuid.uuid4(),
            title=f"Job {i}",
            company_name="Acme",
            dedup_hash=f"h{i}",
        )
        for i in range(5)
    ]
    job_repo.search = AsyncMock(return_value=five_jobs)
    api_spy = mocker.patch.object(fallback_service.jdl_client, "search_jobs")

    result = await fallback_service.search_with_fallback(
        query="test", limit=10, threshold=5, criteria={}
    )
    assert result.fallback_used is False
    api_spy.assert_not_called()

    # Below threshold (1 hit) -- API called
    one_job = [
        Job(
            id=uuid.uuid4(),
            title="Job 0",
            company_name="Acme",
            dedup_hash="h0",
        )
    ]
    job_repo.search = AsyncMock(side_effect=[one_job, one_job])
    mocker.patch.object(
        fallback_service.jdl_client,
        "search_jobs",
        AsyncMock(return_value={"jobs": []}),
    )

    result = await fallback_service.search_with_fallback(
        query="test", limit=10, threshold=5, criteria={}
    )
    # API returned empty -> still no fallback_used
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_api_error_graceful(fallback_service, job_repo, mocker):
    """FR-008: API 5xx -> graceful empty result, no exception raised."""
    import httpx

    job_repo.search = AsyncMock(return_value=[])
    mocker.patch.object(
        fallback_service.jdl_client,
        "search_jobs",
        side_effect=httpx.HTTPStatusError(
            "500 Server Error", request=MagicMock(), response=MagicMock()
        ),
    )

    result = await fallback_service.search_with_fallback(
        query="test", limit=10, threshold=5, criteria={}
    )
    # Graceful degradation -- empty but no exception
    assert result.fallback_used is False
    assert result.total == 0


@pytest.mark.asyncio
async def test_fallback_disabled(fallback_service_disabled, job_repo, mocker):
    """FR-012: fallback_enabled=False -> API never called regardless of DB results."""
    job_repo.search = AsyncMock(return_value=[])
    api_spy = mocker.patch.object(fallback_service_disabled.jdl_client, "search_jobs")

    result = await fallback_service_disabled.search_with_fallback(
        query="test", limit=10, threshold=5, criteria={}
    )
    assert result.fallback_used is False
    api_spy.assert_not_called()


@pytest.mark.asyncio
async def test_malformed_job_dropped(fallback_service, job_repo, mocker):
    """FR-014: Malformed job dropped, valid one kept, dropped_count reported."""
    import uuid
    from datetime import datetime

    from app.core.db.models.job import Job
    from app.core.jdl.schemas import JobCreate, JobSourceCreate

    job_repo.search = AsyncMock(
        side_effect=[
            [],  # first call: below threshold
            [
                Job(
                    id=uuid.uuid4(),
                    title="Good Engineer",
                    company_name="Good Co",
                    dedup_hash="h1",
                )
            ],
        ]
    )
    mocker.patch.object(
        fallback_service.jdl_client,
        "search_jobs",
        AsyncMock(
            return_value={
                "jobs": [
                    {
                        "id": "valid_1",
                        "title": "Good Engineer",
                        "company_name": "Good Co",
                    },
                    {"id": "bad_1"},  # missing required fields
                ]
            }
        ),
    )

    def make_job_create_good():
        return JobCreate(
            title="Good Engineer",
            company_name="Good Co",
            dedup_hash="h1",
            required_skills=[],
            locations=[],
            countries=[],
            seniority=[],
            status="active",
            source=JobSourceCreate(
                source_name="jobdatalake",
                source_job_id="valid_1",
                source_url="https://example.com",
                first_seen_at=datetime.utcnow(),
            ),
        )

    mocker.patch(
        "app.mcp.services.job_fallback_service.normalize_job",
        side_effect=[
            make_job_create_good(),
            ValueError("Missing required fields"),
        ],
    )

    mock_upserted = [
        Job(
            id=uuid.uuid4(),
            title="Good Engineer",
            company_name="Good Co",
            dedup_hash="h1",
            fallback_source="jdl_api",
        )
    ]
    job_repo.upsert_from_fallback = AsyncMock(return_value=mock_upserted)
    mocker.patch.object(fallback_service, "_schedule_embeddings")

    result = await fallback_service.search_with_fallback(
        query="test", limit=10, threshold=5, criteria={}
    )
    assert result.dropped_count == 1


# =========================================================================
# T028-T030: US2 get_job_with_fallback() tests
# =========================================================================


@pytest.mark.asyncio
async def test_get_job_fallback(fallback_service, job_repo, mocker):
    """FR-003: Job ID absent from DB -> fetched from JDL API, upserted, returned."""
    import uuid
    from datetime import datetime

    from app.core.db.models.job import Job
    from app.core.jdl.schemas import JobCreate, JobSourceCreate

    job_id = uuid.uuid4()

    # DB returns None
    job_repo.get_by_id = AsyncMock(return_value=None)
    job_repo.get_by_source_job_id = AsyncMock(return_value=None)

    # JDL API returns job
    mock_raw = {
        "id": "jdl_201",
        "title": "Found Engineer",
        "company_name": "Found Co",
    }
    fallback_service.jdl_client.get_job_by_id = AsyncMock(return_value=mock_raw)

    valid_jc = JobCreate(
        title="Found Engineer",
        company_name="Found Co",
        dedup_hash="h3",
        required_skills=[],
        locations=[],
        countries=[],
        seniority=[],
        status="active",
        source=JobSourceCreate(
            source_name="jobdatalake",
            source_job_id="jdl_201",
            source_url="https://example.com",
            first_seen_at=datetime.utcnow(),
        ),
    )
    mocker.patch(
        "app.mcp.services.job_fallback_service.normalize_job",
        return_value=valid_jc,
    )

    mock_job = Job(
        id=job_id,
        title="Found Engineer",
        company_name="Found Co",
        dedup_hash="h3",
        fallback_source="jdl_api",
    )
    job_repo.upsert_from_fallback = AsyncMock(return_value=[mock_job])
    mocker.patch.object(fallback_service, "_schedule_embeddings")

    result = await fallback_service.get_job_with_fallback(job_id)
    assert result is not None
    assert result.fallback_source == "jdl_api"


@pytest.mark.asyncio
async def test_get_job_in_db_no_api(fallback_service, job_repo, mocker):
    """FR-001: Job already in DB -> returned WITHOUT API call."""
    import uuid

    from app.core.db.models.job import Job

    job_id = uuid.uuid4()
    mock_job = Job(
        id=job_id,
        title="Existing Job",
        company_name="Existing Co",
        dedup_hash="h4",
        fallback_source=None,
    )
    job_repo.get_by_id = AsyncMock(return_value=mock_job)
    api_spy = mocker.patch.object(fallback_service.jdl_client, "get_job_by_id")

    result = await fallback_service.get_job_with_fallback(job_id)
    assert result is not None
    assert result.fallback_source is None  # not from API
    api_spy.assert_not_called()


@pytest.mark.asyncio
async def test_get_job_not_found_anywhere(fallback_service, job_repo, mocker):
    """FR-003: Job not in DB or JDL -> returns None."""
    import uuid

    job_id = uuid.uuid4()
    job_repo.get_by_id = AsyncMock(return_value=None)
    job_repo.get_by_source_job_id = AsyncMock(return_value=None)
    fallback_service.jdl_client.get_job_by_id = AsyncMock(return_value=None)

    result = await fallback_service.get_job_with_fallback(job_id)
    assert result is None


# =========================================================================
# T019 / FR-013: In-flight dedup
# =========================================================================


@pytest.mark.asyncio
async def test_inflight_dedup(fallback_service, job_repo, mocker):
    """FR-013, SC-005: Two simultaneous identical queries -> exactly one API call."""
    import uuid

    from app.core.db.models.job import Job

    job_repo.search = AsyncMock(return_value=[])

    call_count = 0

    async def delayed_search(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {"jobs": [{"id": "jdl_101", "title": "Engineer"}]}

    fallback_service.jdl_client.search_jobs = AsyncMock(side_effect=delayed_search)

    # Mock normalize_job and upsert to complete the flow quickly
    from datetime import datetime

    from app.core.jdl.schemas import JobCreate, JobSourceCreate

    fallback_jc = JobCreate(
        title="Engineer",
        company_name="Acme",
        dedup_hash="h_inflight",
        required_skills=[],
        locations=[],
        countries=[],
        seniority=[],
        status="active",
        source=JobSourceCreate(
            source_name="jobdatalake",
            source_job_id="jdl_101",
            source_url="https://example.com",
            first_seen_at=datetime.now(),
        ),
    )
    mocker.patch(
        "app.mcp.services.job_fallback_service.normalize_job",
        return_value=fallback_jc,
    )

    mock_job = Job(
        id=uuid.uuid4(),
        title="Engineer",
        company_name="Acme",
        dedup_hash="h_inflight",
        fallback_source="jdl_api",
    )
    job_repo.upsert_from_fallback = AsyncMock(return_value=[mock_job])

    # Use a counter to return empty [] on first calls, then populated results
    _search_count = 0

    async def search_side_effect(*args, **kwargs):
        nonlocal _search_count
        _search_count += 1
        return [] if _search_count <= 2 else [mock_job]

    job_repo.search = AsyncMock(side_effect=search_side_effect)
    mocker.patch.object(fallback_service, "_schedule_embeddings")

    async def run_query():
        return await fallback_service.search_with_fallback(
            query="python engineer", limit=10, threshold=5, criteria={}
        )

    r1, r2 = await asyncio.gather(run_query(), run_query())
    assert call_count == 1, f"Expected 1 API call, got {call_count}"
    assert r1.fallback_used is True
    assert r2.fallback_used is True


# =========================================================================
# T036 / FR-012: JDL client init failure disables fallback
# =========================================================================


def test_jdl_client_init_failure_disables_fallback():
    """FR-012: JDL client init failure -> fallback_enabled=False with warning."""
    from app.mcp.services.job_fallback_service import JobFallbackService

    service = JobFallbackService(
        job_repo=MagicMock(),
        jdl_client=None,
        settings=MagicMock(fallback_enabled=True),
    )
    assert service._fallback_enabled is False
