"""Shared test fixtures for fallback-related tests."""

from unittest.mock import MagicMock

import pytest

from app.core.config.settings import Settings


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
