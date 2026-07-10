import uuid

import pytest
from langgraph.graph import END

from app.core.jdl.schemas import JobSearchResult
from app.graph.graph_state import GeneratedResponse, JobClaim, QAGraphState
from app.graph.scoring_nodes import MAX_HEURISTIC_ATTEMPTS, heuristic_check


def make_job(job_id: uuid.UUID) -> JobSearchResult:
    return JobSearchResult(
        id=job_id,
        dedup_hash=str(job_id),
        title="Software Engineer",
        company_name="Acme",
        rrf_score=0.9,
    )


def make_state(claims: list[JobClaim], jobs: list[JobSearchResult], attempts=0):
    return QAGraphState(
        user_query="find me a job",
        retrieved_jobs=jobs,
        draft_response=GeneratedResponse(
            insufficient_data=False, summary="here you go", claims=claims
        ),
        heuristic_attempts=attempts,
    )


@pytest.mark.asyncio
async def test_grounded_claims_pass_through():
    job = make_job(uuid.uuid4())
    state = make_state([JobClaim(text="matches", job_id=str(job.id))], [job])

    result = await heuristic_check(state)

    assert result.goto == END
    assert result.update is None


@pytest.mark.asyncio
async def test_ungrounded_claim_retries_generation():
    job = make_job(uuid.uuid4())
    bogus_id = str(uuid.uuid4())
    state = make_state([JobClaim(text="fabricated", job_id=bogus_id)], [job])

    result = await heuristic_check(state)

    assert result.goto == "generate_draft"
    assert result.update["heuristic_attempts"] == 1
    assert bogus_id in result.update["grounding_error"]


@pytest.mark.asyncio
async def test_exhausted_attempts_falls_back_to_insufficient_data():
    job = make_job(uuid.uuid4())
    bogus_id = str(uuid.uuid4())
    state = make_state(
        [JobClaim(text="fabricated", job_id=bogus_id)],
        [job],
        attempts=MAX_HEURISTIC_ATTEMPTS - 1,
    )

    result = await heuristic_check(state)

    assert result.goto == END
    assert result.update["draft_response"].insufficient_data is True
    assert result.update["draft_response"].claims == []


@pytest.mark.asyncio
async def test_insufficient_data_short_circuits_without_checking_claims():
    state = QAGraphState(
        user_query="find me a job",
        retrieved_jobs=[],
        draft_response=GeneratedResponse(
            insufficient_data=True, summary="no jobs found", claims=[]
        ),
    )

    result = await heuristic_check(state)

    assert result.goto == END
    assert result.update is None
