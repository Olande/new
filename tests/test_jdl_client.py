"""Tests for app.core.jdl.client.JobDataLakeClient."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_job_by_id_found():
    from app.core.jdl.client import JobDataLakeClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "jdl_001", "title": "Engineer"}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client = JobDataLakeClient(api_key="test-key")
    client.client = mock_client
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
