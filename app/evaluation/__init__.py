"""Retrieval evaluation harness for CareerPilot hybrid search.

Two entry points:
  - ``python -m app.evaluation.run_local``   — offline IR metrics (fast iteration)
  - ``python -m app.evaluation.run_eval``    — LangSmith aevaluate + regression gate

Metrics are computed with ``ir-measures``. ``no_match`` examples are excluded from
ranked metrics (nDCG / RR / Recall) and reported separately.
"""

from app.evaluation.constants import (
    DEFAULT_SEARCH_PARAMS,
    RETRIEVAL_DATASET,
    SearchParams,
)
from app.evaluation.metrics import compute_aggregate_metrics, format_metrics

__all__ = [
    "DEFAULT_SEARCH_PARAMS",
    "RETRIEVAL_DATASET",
    "SearchParams",
    "compute_aggregate_metrics",
    "format_metrics",
]
