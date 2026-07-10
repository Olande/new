"""Compare current LangSmith experiment against the prior one for regression."""

from __future__ import annotations

from langsmith import Client
from loguru import logger

from app.evaluation.constants import (
    MRR_REGRESSION_THRESHOLD,
    NDCG_REGRESSION_THRESHOLD,
    RETRIEVAL_DATASET,
)


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
    """
    Return True if a regression is detected vs the previous experiment.

    Only compares metrics that produced non-null scores (no_match examples
    with score=None are already excluded by get_feedback_avg).
    """
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
