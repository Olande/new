"""Tests for app.mcp.services.job_fallback_service.JobFallbackService."""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.db.models.job import Job
from app.core.jdl.schemas import JobCreate, JobSourceCreate
from app.mcp.services.job_fallback_service import JobFallbackService


def test_job_fallback_service_instantiation():
    """Service can be created with required dependencies."""
    service = JobFallbackService(
        job_repo=MagicMock(),
        jdl_client=MagicMock(),
        settings=MagicMock(fallback_enabled=True),
    )
    assert service is not None


@pytest.mark.asyncio
async def test_empty_db_triggers_fallback(fallback_service, job_repo, mocker):
    """FR-002, FR-004: DB returns 0 hits -> API called, upsert runs, re-query returns results."""
    job_repo.search = AsyncMock(return_value=[])
    fallback_service.jdl_client.search_jobs = AsyncMock(
        return_value={
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
    )

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
    job_repo.search = AsyncMock(side_effect=[[], mock_jobs])
    mocker.patch.object(fallback_service, "_schedule_embeddings")
    result = await fallback_service.search_with_fallback(
        query="python engineer", limit=10, threshold=5, criteria={}
    )
    assert result.fallback_used is True
    assert result.total >= 2


@pytest.mark.asyncio
async def test_populated_db_no_fallback(fallback_service, job_repo, mocker):
    """FR-001, FR-006: DB returns >= threshold hits -> API NEVER called."""
    mock_jobs = [
        Job(id=uuid.uuid4(), title=f"Job {i}", company_name="Acme", dedup_hash=f"h{i}")
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
    five_jobs = [
        Job(id=uuid.uuid4(), title=f"Job {i}", company_name="Acme", dedup_hash=f"h{i}")
        for i in range(5)
    ]
    job_repo.search = AsyncMock(return_value=five_jobs)
    api_spy = mocker.patch.object(fallback_service.jdl_client, "search_jobs")
    result = await fallback_service.search_with_fallback(
        query="test", limit=10, threshold=5, criteria={}
    )
    assert result.fallback_used is False
    api_spy.assert_not_called()
    one_job = [
        Job(id=uuid.uuid4(), title="Job 0", company_name="Acme", dedup_hash="h0")
    ]
    job_repo.search = AsyncMock(side_effect=[one_job, one_job])
    mocker.patch.object(
        fallback_service.jdl_client, "search_jobs", AsyncMock(return_value={"jobs": []})
    )
    result = await fallback_service.search_with_fallback(
        query="test", limit=10, threshold=5, criteria={}
    )
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_api_error_graceful(fallback_service, job_repo, mocker):
    """FR-008: API 5xx -> graceful empty result, no exception raised."""
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
    job_repo.search = AsyncMock(
        side_effect=[
            [],
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
                    {"id": "bad_1"},
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
        side_effect=[make_job_create_good(), ValueError("Missing required fields")],
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


@pytest.mark.asyncio
async def test_get_job_fallback(fallback_service, job_repo, mocker):
    """FR-003: Job ID absent from DB -> fetched from JDL API, upserted, returned."""
    job_id = uuid.uuid4()
    job_repo.get_by_id = AsyncMock(return_value=None)
    job_repo.get_by_source_job_id = AsyncMock(return_value=None)
    mock_raw = {"id": "jdl_201", "title": "Found Engineer", "company_name": "Found Co"}
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
        "app.mcp.services.job_fallback_service.normalize_job", return_value=valid_jc
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
    assert result.fallback_source is None
    api_spy.assert_not_called()


@pytest.mark.asyncio
async def test_get_job_not_found_anywhere(fallback_service, job_repo, mocker):
    """FR-003: Job not in DB or JDL -> returns None."""
    job_id = uuid.uuid4()
    job_repo.get_by_id = AsyncMock(return_value=None)
    job_repo.get_by_source_job_id = AsyncMock(return_value=None)
    fallback_service.jdl_client.get_job_by_id = AsyncMock(return_value=None)
    result = await fallback_service.get_job_with_fallback(job_id)
    assert result is None


@pytest.mark.asyncio
async def test_inflight_dedup(fallback_service, job_repo, mocker):
    """FR-013, SC-005: Two simultaneous identical queries -> exactly one API call."""
    job_repo.search = AsyncMock(return_value=[])
    call_count = 0

    async def delayed_search(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {"jobs": [{"id": "jdl_101", "title": "Engineer"}]}

    fallback_service.jdl_client.search_jobs = AsyncMock(side_effect=delayed_search)
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
        "app.mcp.services.job_fallback_service.normalize_job", return_value=fallback_jc
    )
    mock_job = Job(
        id=uuid.uuid4(),
        title="Engineer",
        company_name="Acme",
        dedup_hash="h_inflight",
        fallback_source="jdl_api",
    )
    job_repo.upsert_from_fallback = AsyncMock(return_value=[mock_job])
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


def test_jdl_client_init_failure_disables_fallback():
    """FR-012: JDL client init failure -> fallback_enabled=False with warning."""
    service = JobFallbackService(
        job_repo=MagicMock(),
        jdl_client=None,
        settings=MagicMock(fallback_enabled=True),
    )
    assert service._fallback_enabled is False
