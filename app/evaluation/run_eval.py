import asyncio
import sys
from statistics import mean

from dotenv import load_dotenv
from langsmith import Client, aevaluate
from loguru import logger

from app.core.config.settings import settings
from app.evaluation.metrics import (
    MRR_REGRESSION_THRESHOLD,
    NDCG_REGRESSION_THRESHOLD,
    RETRIEVAL_EVALUATORS,
)
from app.evaluation.search import (
    DEFAULT_SEARCH_PARAMS,
    RETRIEVAL_DATASET,
    retrieval_target,
)

_ = load_dotenv()

REGRESSION_THRESHOLDS = {
    "ndcg_at_10": NDCG_REGRESSION_THRESHOLD,
    "mrr": MRR_REGRESSION_THRESHOLD,
}


def get_feedback_avg(client: Client, project_name: str, metric_name: str) -> float:
    try:
        runs = list(client.list_runs(project_name=project_name))
        if not runs:
            return 0.0
        feedbacks = client.list_feedback(run_ids=[run.id for run in runs])
        scores = [
            float(fb.score)
            for fb in feedbacks
            if fb.key == metric_name and fb.score is not None
        ]
        return mean(scores) if scores else 0.0
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
    projects_by_name = {p.name: p for p in projects}

    current_project = projects_by_name.get(current_project_name)
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
    for metric_name, threshold in REGRESSION_THRESHOLDS.items():
        current_score = get_feedback_avg(client, current_project.name, metric_name)
        prior_score = get_feedback_avg(client, prior_project.name, metric_name)

        logger.info(
            f"Current {metric_name}: {current_score:.4f}, "
            f"Prior {metric_name}: {prior_score:.4f}"
        )

        drop = relative_drop(prior_score, current_score)
        if drop is not None and drop > threshold:
            logger.error(
                f"Regression detected in {metric_name}! Dropped by {drop * 100:.1f}% "
                f"(> {threshold * 100:.1f}%)"
            )
            has_regression = True

    return has_regression


async def run_evaluations() -> None:
    if not settings.langsmith_api_key:
        logger.error("LANGSMITH_API_KEY not set. Cannot run evaluations.")
        sys.exit(1)

    client = Client()
    params = DEFAULT_SEARCH_PARAMS
    logger.info(
        "Running retrieval evaluation on dataset={} with params={}",
        RETRIEVAL_DATASET,
        params.as_dict(),
    )

    async def target(inputs: dict) -> dict:
        return await retrieval_target(inputs, params=params)

    retrieval_results = await aevaluate(
        target,
        data=RETRIEVAL_DATASET,
        evaluators=RETRIEVAL_EVALUATORS,
        experiment_prefix="hybrid-retrieval",
        metadata={"search_params": params.as_dict(), "dataset": RETRIEVAL_DATASET},
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


def main() -> None:
    asyncio.run(run_evaluations())


if __name__ == "__main__":
    main()
