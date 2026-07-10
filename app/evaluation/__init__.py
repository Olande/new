"""Retrieval evaluation harness for CareerPilot hybrid search.

Two entry points:
  - ``python -m app.evaluation.run_local``  — offline IR metrics (fast iteration)
  - ``python -m app.evaluation.run_eval``   — LangSmith aevaluate + regression gate

Metrics are computed with ``ir-measures``. ``no_match`` examples are excluded from
ranked metrics (nDCG / RR / Recall) and reported separately.
"""

from app.evaluation.constants import MATCHING_STYLES, NO_MATCH_STYLE
from app.evaluation.metrics import compute_aggregate_metrics, format_metrics

__all__ = [
    "MATCHING_STYLES",
    "NO_MATCH_STYLE",
    "compute_aggregate_metrics",
    "format_metrics",
]
