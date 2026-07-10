"""Shim — evaluators live in ``app.evaluation.evaluators``."""

from app.evaluation.evaluators import (  # noqa: F401
    RETRIEVAL_EVALUATORS,
    mrr,
    ndcg_at_10,
    ndcg_at_20,
    recall_at_10,
    recall_at_20,
)
