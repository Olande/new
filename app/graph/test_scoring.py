import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.types import Overwrite, Send

from app.core.jdl.schemas import JobSearchCriteria, JobSearchResult
from app.graph.graph_state import JobScore, QAGraphState
from app.graph.query_nodes import route_to_scoring
from app.graph.scoring_nodes import DEFAULT_TOP_N, compile_results


def make_job(job_id: uuid.UUID, title="Software Engineer") -> JobSearchResult:
    return JobSearchResult(
        id=job_id,
        dedup_hash=str(job_id),
        title=title,
        company_name="Acme",
        rrf_score=0.9,
    )


def test_route_to_scoring_fans_out_one_send_per_job():
    jobs = [make_job(uuid.uuid4()) for _ in range(3)]
    state = QAGraphState(user_query="find me a job", retrieved_jobs=jobs)

    result = route_to_scoring(state)

    assert isinstance(result, list)
    assert all(isinstance(s, Send) for s in result)
    assert len(result) == 3
    assert {s.arg["job_to_score"].id for s in result} == {j.id for j in jobs}
    assert all(s.node == "score_candidate" for s in result)


def test_route_to_scoring_skips_fanout_when_no_jobs():
    state = QAGraphState(user_query="find me a job", retrieved_jobs=[])

    result = route_to_scoring(state)

    assert result == "generate_draft"


def test_compile_results_sorts_and_truncates():
    jobs = [make_job(uuid.uuid4(), title=f"Job {i}") for i in range(7)]
    scores = [
        JobScore(job_id=str(j.id), fit_score=score, rationale="r")
        for j, score in zip(jobs, [0.1, 0.9, 0.3, 0.95, 0.2, 0.5, 0.8], strict=False)
    ]
    state = QAGraphState(
        user_query="find me a job", retrieved_jobs=jobs, job_scores=scores
    )

    result = compile_results(state)

    assert len(result["retrieved_jobs"]) == DEFAULT_TOP_N
    # Highest fit_score first: jobs[3] (0.95), jobs[1] (0.9), jobs[6] (0.8), ...
    assert result["retrieved_jobs"][0].id == jobs[3].id
    assert result["retrieved_jobs"][1].id == jobs[1].id
    assert isinstance(result["job_scores"], Overwrite)
    assert result["job_scores"].value == []


def test_compile_results_respects_explicit_limit():
    jobs = [make_job(uuid.uuid4()) for _ in range(4)]
    scores = [JobScore(job_id=str(j.id), fit_score=0.5, rationale="r") for j in jobs]
    state = QAGraphState(
        user_query="find me a job",
        retrieved_jobs=jobs,
        job_scores=scores,
        extracted_criteria=JobSearchCriteria(limit=2),
    )

    result = compile_results(state)

    assert len(result["retrieved_jobs"]) == 2


@pytest.mark.asyncio
async def test_score_candidate_success():
    job = make_job(uuid.uuid4(), title="Python Engineer")
    state = {"user_query": "Python jobs", "job_to_score": job}

    mock_score = JobScore(job_id=str(job.id), fit_score=0.9, rationale="Good match")
    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(return_value=mock_score)

    with patch("app.graph.scoring_nodes.get_fast_model") as mock_get_model:
        mock_get_model.return_value.with_structured_output.return_value = mock_model

        from app.graph.scoring_nodes import score_candidate

        result = await score_candidate(state)

        assert result == {"job_scores": [mock_score]}
        assert mock_score.job_id == str(job.id)
        mock_get_model.return_value.with_structured_output.assert_called_once_with(
            JobScore
        )
        mock_model.ainvoke.assert_called_once()
