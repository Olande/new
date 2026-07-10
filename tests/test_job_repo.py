"""Tests for app.mcp.repositories.job_repo.JobRepository."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_by_source_job_id_found():
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
    from app.mcp.repositories.job_repo import JobRepository

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = JobRepository(session=mock_session)
    job = await repo.get_by_source_job_id("nonexistent")
    assert job is None


@pytest.mark.asyncio
async def test_upsert_from_fallback_empty():
    from app.mcp.repositories.job_repo import JobRepository

    repo = JobRepository(session=MagicMock())
    result = await repo.upsert_from_fallback([])
    assert result == []
