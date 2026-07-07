import asyncio
import sys
import textwrap

from dotenv import load_dotenv
from langsmith import Client, aevaluate
from loguru import logger

from app.config.settings import settings
from app.evaluation.evaluators import (
    hallucination_evaluator,
    mrr,
    ndcg_at_10,
    rubric_evaluator,
)

_ = load_dotenv()

NDCG_REGRESSION_THRESHOLD = 0.05
MRR_REGRESSION_THRESHOLD = 0.05
RETRIEVAL_DATASET = "careerpilot-matching-eval"
GENERATION_DATASET = "careerpilot-generation-eval"


async def retrieval_target(inputs: dict) -> dict:
    from sqlalchemy import select

    from app.db.base import async_session
    from app.db.models.job_description import JobDescription
    from app.retrieval.embeddings import get_embeddings_client
    from app.retrieval.search import hybrid_search

    query = inputs.get("query", "")

    async with async_session() as session:
        embeddings = get_embeddings_client()
        query_embedding = await embeddings.aembed_query(query)
        candidates = await hybrid_search(
            session, query_embedding=query_embedding, query_text=query, k=10
        )

        job_ids = [c.job.id for c in candidates]
        descriptions = {}
        if job_ids:
            stmt = select(JobDescription).where(JobDescription.job_id.in_(job_ids))
            result = await session.execute(stmt)
            descriptions = {desc.job_id: desc.cleaned_text for desc in result.scalars()}

    ranked_jobs = []
    for c in candidates:
        desc = descriptions.get(c.job.id, "")
        ranked_jobs.append(
            {
                "id": str(c.job.id),
                "title": c.job.title,
                "company_name": c.job.company_name,
                "required_skills": list(c.job.required_skills)
                if c.job.required_skills
                else [],
                "description_snippet": textwrap.shorten(
                    desc, width=500, placeholder="..."
                )
                if desc
                else "",
                "score": float(c.score),
            }
        )

    return {"ranked_jobs": ranked_jobs}


async def generation_target(inputs: dict) -> dict:
    from app.agents.resume_agent import generate_resume_draft

    draft = await generate_resume_draft(
        career_memory=inputs.get("career_memory", []),
        job_title=inputs.get("job_title", ""),
        company_name=inputs.get("company_name", ""),
        required_skills=inputs.get("required_skills", []),
        job_description=inputs.get("job_description", ""),
        critique=inputs.get("critique"),
    )
    return {"resume_draft": draft}


def get_feedback_avg(client: Client, project_name: str, metric_name: str) -> float:
    try:
        runs = list(client.list_runs(project_name=project_name))
        if not runs:
            return 0.0
        run_ids = [run.id for run in runs]
        feedbacks = list(client.list_feedback(run_ids=run_ids))
        scores = [
            float(fb.score)
            for fb in feedbacks
            if fb.key == metric_name and fb.score is not None
        ]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)
    except Exception as e:
        logger.warning(f"Error calculating feedback average for {project_name}: {e}")
        return 0.0


def relative_drop(prior: float, current: float) -> float | None:
    if prior <= 0:
        return None
    return (prior - current) / prior


def check_retrieval_regression(client: Client, current_project_name: str) -> bool:
    dataset = next(client.list_datasets(dataset_name=RETRIEVAL_DATASET), None)
    if dataset is None:
        logger.info("No dataset found, skipping regression check.")
        return False

    projects = sorted(
        client.list_projects(reference_dataset_id=dataset.id),
        key=lambda p: p.start_time or p.created_at,
        reverse=True,
    )

    current_project = next(
        (p for p in projects if p.name == current_project_name), None
    )
    if current_project is None:
        logger.warning(
            f"Current project {current_project_name!r} not found among experiments, "
            "skipping regression check."
        )
        return False

    prior_project = next((p for p in projects if p.name != current_project_name), None)
    if prior_project is None:
        logger.info("No prior experiment to compare against.")
        return False

    has_regression = False

    for metric_name, threshold in (
        ("ndcg_at_10", NDCG_REGRESSION_THRESHOLD),
        ("mrr", MRR_REGRESSION_THRESHOLD),
    ):
        current_score = get_feedback_avg(client, current_project.name, metric_name)
        prior_score = get_feedback_avg(client, prior_project.name, metric_name)

        logger.info(
            f"Current {metric_name}: {current_score:.4f}, "
            f"Prior {metric_name}: {prior_score:.4f}"
        )

        drop = relative_drop(prior_score, current_score)
        if drop is None:
            continue

        if drop > threshold:
            logger.error(
                f"Regression detected in {metric_name}! Dropped by {drop * 100:.1f}% "
                f"(> {threshold * 100:.1f}%)"
            )
            has_regression = True

    return has_regression


async def run_evaluations():
    if not settings.langsmith_api_key:
        logger.error("LANGSMITH_API_KEY not set. Cannot run evaluations.")
        sys.exit(1)

    client = Client()

    logger.info("Running retrieval evaluation...")
    retrieval_results = await aevaluate(
        retrieval_target,
        data=RETRIEVAL_DATASET,
        evaluators=[ndcg_at_10, mrr],
        experiment_prefix="hybrid-retrieval",
    )

    logger.info("Running generation evaluation...")
    await aevaluate(
        generation_target,
        data=GENERATION_DATASET,
        evaluators=[rubric_evaluator, hallucination_evaluator],
        experiment_prefix="resume-generation",
        max_concurrency=5,
    )

    has_error = False
    try:
        has_error = check_retrieval_regression(
            client, retrieval_results.experiment_name
        )
    except Exception as e:
        logger.warning(f"Error comparing retrieval metrics: {e}")

    logger.info("Evaluations completed.")
    if has_error:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_evaluations())
