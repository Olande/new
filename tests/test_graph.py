import uuid

import pytest
from langgraph.graph import END

from app.core.jdl.schemas import JobSearchCriteria, JobSearchResult
from app.graph.graph_state import (
    CritiqueResult,
    GeneratedResponse,
    JobClaim,
    JobScore,
    QAGraphState,
)
from app.graph.scoring_nodes import (
    MAX_HEURISTIC_ATTEMPTS,
    MAX_VERIFICATION_ATTEMPTS,
    compile_results,
    heuristic_check,
    llm_critic,
)


def make_job(job_id: uuid.UUID) -> JobSearchResult:
    return JobSearchResult(
        id=job_id,
        dedup_hash=str(job_id),
        title="Software Engineer",
        company_name="Acme",
        rrf_score=0.9,
    )


def make_state(
    claims: list[JobClaim],
    jobs: list[JobSearchResult],
    attempts=0,
    verification_attempts=0,
):
    return QAGraphState(
        user_query="find me a job",
        retrieved_jobs=jobs,
        draft_response=GeneratedResponse(
            insufficient_data=False, summary="here you go", claims=claims
        ),
        heuristic_attempts=attempts,
        verification_attempts=verification_attempts,
    )


@pytest.mark.asyncio
async def test_grounded_claims_pass_to_critic():
    """Phase 3: heuristic pass should route to llm_critic, not directly to END."""
    job = make_job(uuid.uuid4())
    state = make_state([JobClaim(text="matches", job_id=str(job.id))], [job])

    result = await heuristic_check(state)

    assert result.goto == "llm_critic"
    # No update on clean pass
    assert result.update is None or result.update == {}


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


# ---- Phase 3 new: LLM critic tests ----


class FakeValidModel:
    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, prompt):
        return CritiqueResult(is_valid=True, issues=[], suggested_fix=None)


class FakeInvalidModel:
    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, prompt):
        return CritiqueResult(
            is_valid=False,
            issues=["Salary inflated from 80k to 150k"],
            suggested_fix="Remove salary claim or cite exact range from job",
        )


@pytest.mark.asyncio
async def test_llm_critic_valid_passes(monkeypatch):
    job = make_job(uuid.uuid4())
    state = make_state([JobClaim(text="ok", job_id=str(job.id))], [job])

    monkeypatch.setattr(
        "app.graph.scoring_nodes.get_frontier_model", lambda: FakeValidModel()
    )

    result = await llm_critic(state)
    assert result.goto == END
    assert result.update["verification_attempts"] == 0


@pytest.mark.asyncio
async def test_llm_critic_invalid_retries(monkeypatch):
    job = make_job(uuid.uuid4())
    state = make_state(
        [JobClaim(text="ok", job_id=str(job.id))], [job], verification_attempts=0
    )

    monkeypatch.setattr(
        "app.graph.scoring_nodes.get_frontier_model", lambda: FakeInvalidModel()
    )

    result = await llm_critic(state)
    assert result.goto == "generate_draft"
    assert result.update["verification_attempts"] == 1
    assert "Salary inflated" in result.update["critique_feedback"]


@pytest.mark.asyncio
async def test_llm_critic_exhausted_falls_back(monkeypatch):
    job = make_job(uuid.uuid4())
    state = make_state(
        [JobClaim(text="ok", job_id=str(job.id))],
        [job],
        verification_attempts=MAX_VERIFICATION_ATTEMPTS - 1,
    )

    monkeypatch.setattr(
        "app.graph.scoring_nodes.get_frontier_model", lambda: FakeInvalidModel()
    )

    result = await llm_critic(state)
    assert result.goto == END
    assert result.update["draft_response"].insufficient_data is True


@pytest.mark.asyncio
async def test_state_isolation_compile_resets_scores():
    """Verifies compile_results uses Overwrite to prevent bleed."""
    j1_id = uuid.uuid4()
    j2_id = uuid.uuid4()
    j1 = make_job(j1_id)
    j2 = make_job(j2_id)
    state = QAGraphState(
        user_query="test",
        extracted_criteria=JobSearchCriteria(limit=1),
        retrieved_jobs=[j1, j2],
        job_scores=[
            JobScore(job_id=str(j1_id), fit_score=0.9, rationale="good"),
            JobScore(job_id=str(j2_id), fit_score=0.2, rationale="bad"),
        ],
    )

    update = compile_results(state)
    # Should keep only top job (j1) and reset scores via Overwrite
    assert len(update["retrieved_jobs"]) == 1
    assert str(update["retrieved_jobs"][0].id) == str(j1_id)
    # Overwrite marker should be present (langgraph types)
    assert update["job_scores"].__class__.__name__ == "Overwrite"
