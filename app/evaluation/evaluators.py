from langsmith.schemas import Example, Run
from loguru import logger

from app.evaluation.metrics import (
    expected_job_id_of,
    per_query_metrics,
    query_style_of,
)

# Cache per-run metric dicts so ndcg/mrr/recall share one ir_measures pass
_metrics_cache: dict[str, dict[str, float] | None] = {}


def _extract_ranked_job_ids(run: Run) -> list[str]:
    outputs = run.outputs or {}
    ranked_jobs = outputs.get("ranked_jobs") or []
    if ranked_jobs and isinstance(ranked_jobs[0], dict):
        return [str(job["id"]) for job in ranked_jobs]
    return [str(job_id) for job_id in outputs.get("ranked_job_ids", [])]


def _metrics_for(run: Run, example: Example) -> dict[str, float] | None:
    cache_key = str(run.id)
    if cache_key in _metrics_cache:
        return _metrics_cache[cache_key]

    expected = expected_job_id_of(example)
    if expected is None:
        _metrics_cache[cache_key] = None
        return None

    ranked = _extract_ranked_job_ids(run)
    result = per_query_metrics(str(example.id), expected, ranked)
    _metrics_cache[cache_key] = result
    return result


def _score(run: Run, example: Example, metric_key: str, feedback_key: str) -> dict:
    try:
        outputs = run.outputs or {}
        if not outputs.get("ranked_jobs") and not outputs.get("ranked_job_ids"):
            # Empty retrieval — 0 for matching, skip-style 0 for no_match too
            return {"key": feedback_key, "score": 0.0}

        metrics = _metrics_for(run, example)
        if metrics is None:
            # no_match: do not poison nDCG/RR aggregates with fake labels
            return {
                "key": feedback_key,
                "score": None,
                "comment": f"skipped ({query_style_of(example)} / no expected_job_id)",
            }

        return {"key": feedback_key, "score": float(metrics.get(metric_key, 0.0))}
    except Exception as e:
        logger.error(f"Error computing {feedback_key}: {e}")
        return {"key": feedback_key, "score": 0.0, "comment": str(e)}


def ndcg_at_10(run: Run, example: Example) -> dict:
    return _score(run, example, "nDCG@10", "ndcg_at_10")


def ndcg_at_20(run: Run, example: Example) -> dict:
    return _score(run, example, "nDCG@20", "ndcg_at_20")


def mrr(run: Run, example: Example) -> dict:
    return _score(run, example, "RR", "mrr")


def recall_at_10(run: Run, example: Example) -> dict:
    return _score(run, example, "Recall@10", "recall_at_10")


def recall_at_20(run: Run, example: Example) -> dict:
    return _score(run, example, "Recall@20", "recall_at_20")


RETRIEVAL_EVALUATORS = [ndcg_at_10, ndcg_at_20, mrr, recall_at_10, recall_at_20]
