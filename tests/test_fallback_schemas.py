"""Tests for fallback-related models and schemas."""

import uuid

from app.core.db.models.job import Job
from app.mcp.mcp_schemas import JobDetailOutput, JobHit, SearchJobsOutput

_JOB_HIT_KWARGS = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Engineer",
    "company_name": "Acme",
    "score": 0.95,
}


def test_job_model_has_fallback_source():
    """FR-011: Job model supports fallback_source column."""
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
    job = Job(
        id=uuid.uuid4(),
        title="Test Engineer",
        dedup_hash="test_hash_002",
        company_name="Acme",
    )
    assert job.fallback_source is None


def test_job_hit_has_fallback_source():
    """FR-011: JobHit carries fallback_source attribution."""
    hit = JobHit(**_JOB_HIT_KWARGS, fallback_source="jdl_api")
    assert hit.fallback_source == "jdl_api"


def test_job_hit_fallback_source_default_none():
    """Backward compat: fallback_source defaults to None."""
    hit = JobHit(**_JOB_HIT_KWARGS)
    assert hit.fallback_source is None


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
