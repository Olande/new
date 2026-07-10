from collections import defaultdict
from typing import Any

import ir_measures
from ir_measures import RR, R, nDCG

from app.evaluation.constants import MATCHING_STYLES, NO_MATCH_STYLE

# Primary measures reported for matching queries
MEASURES = [nDCG @ 10, nDCG @ 20, RR, R @ 10, R @ 20]

# Friendly keys for printing / JSON
_MEASURE_KEYS = {
    nDCG @ 10: "nDCG@10",
    nDCG @ 20: "nDCG@20",
    RR: "RR",
    R @ 10: "Recall@10",
    R @ 20: "Recall@20",
}


def query_style_of(example: Any) -> str:
    """Read query_style from LangSmith example metadata (or inputs fallback)."""
    meta = getattr(example, "metadata", None) or {}
    if isinstance(meta, dict) and meta.get("query_style"):
        return str(meta["query_style"])
    inputs = getattr(example, "inputs", None) or {}
    if isinstance(inputs, dict) and inputs.get("query_style"):
        return str(inputs["query_style"])
    return "unknown"


def expected_job_id_of(example: Any) -> str | None:
    """Return expected job id, or None for no_match / missing labels."""
    outputs = getattr(example, "outputs", None) or {}
    raw = outputs.get("expected_job_id")
    if raw is None or raw == "" or str(raw).lower() == "none":
        return None
    return str(raw)


def is_matching_example(example: Any) -> bool:
    style = query_style_of(example)
    if style == NO_MATCH_STYLE:
        return False
    if style in MATCHING_STYLES:
        return expected_job_id_of(example) is not None
    # Unknown style: treat as matching only when a real job id is present
    return expected_job_id_of(example) is not None


def ranked_ids_to_run(
    qid: str, ranked_job_ids: list[str]
) -> dict[str, dict[str, float]]:
    """Build an ir-measures run dict from an ordered id list (rank → descending score)."""
    return {
        qid: {
            job_id: float(len(ranked_job_ids) - rank)
            for rank, job_id in enumerate(ranked_job_ids)
        }
    }


def scores_to_run(
    qid: str, id_to_score: dict[str, float]
) -> dict[str, dict[str, float]]:
    return {qid: {str(k): float(v) for k, v in id_to_score.items()}}


def build_qrels_and_run_from_rankings(
    examples: list[Any],
    rankings: dict[str, list[str] | dict[str, float]],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, float]], list[str]]:
    """
    Build qrels/run for matching examples only.

    ``rankings`` maps query_id -> ordered job id list OR id->score map.
    Returns (qrels, run, skipped_query_ids) where skipped are no_match / unlabeled.
    """
    qrels: dict[str, dict[str, int]] = {}
    run: dict[str, dict[str, float]] = {}
    skipped: list[str] = []

    for example in examples:
        qid = str(example.id)
        if not is_matching_example(example):
            skipped.append(qid)
            continue

        expected = expected_job_id_of(example)
        assert expected is not None
        qrels[qid] = {expected: 1}

        ranking = rankings.get(qid, {})
        if isinstance(ranking, dict):
            run[qid] = {str(k): float(v) for k, v in ranking.items()}
        else:
            run[qid] = {
                str(job_id): float(len(ranking) - rank)
                for rank, job_id in enumerate(ranking)
            }

    return qrels, run, skipped


def _to_friendly(raw: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for measure, value in raw.items():
        key = _MEASURE_KEYS.get(measure, str(measure))
        out[key] = float(value) if value is not None else 0.0
    return out


def compute_aggregate_metrics(
    qrels: dict[str, dict[str, int]],
    run: dict[str, dict[str, float]],
    measures: list | None = None,
) -> dict[str, float]:
    """Aggregate IR metrics over the provided qrels/run (matching queries only)."""
    if not qrels:
        return {key: 0.0 for key in _MEASURE_KEYS.values()}
    measures = measures or MEASURES
    raw = ir_measures.calc_aggregate(measures, qrels, run)
    return _to_friendly(raw)


def compute_metrics_by_style(
    examples: list[Any],
    rankings: dict[str, list[str] | dict[str, float]],
) -> dict[str, Any]:
    """
    Compute overall + per-style metrics, plus a no_match contamination summary.

    Contamination for no_match: fraction of no_match queries that returned ≥1 hit
    (any result). Useful as a soft negative check when the index is golden-only.
    """
    by_style: dict[str, list[Any]] = defaultdict(list)
    for ex in examples:
        by_style[query_style_of(ex)].append(ex)

    overall_qrels, overall_run, skipped = build_qrels_and_run_from_rankings(
        examples, rankings
    )
    result: dict[str, Any] = {
        "overall": compute_aggregate_metrics(overall_qrels, overall_run),
        "n_matching": len(overall_qrels),
        "n_skipped_no_match": len(skipped),
        "by_style": {},
        "no_match": {},
    }

    for style, style_examples in sorted(by_style.items()):
        if style == NO_MATCH_STYLE:
            continue
        qrels, run, _ = build_qrels_and_run_from_rankings(style_examples, rankings)
        if not qrels:
            continue
        result["by_style"][style] = {
            "n": len(qrels),
            **compute_aggregate_metrics(qrels, run),
        }

    no_match_examples = by_style.get(NO_MATCH_STYLE, [])
    if no_match_examples:
        with_hits = 0
        empty = 0
        for ex in no_match_examples:
            qid = str(ex.id)
            ranking = rankings.get(qid, {})
            n_hits = len(ranking) if ranking is not None else 0
            if n_hits > 0:
                with_hits += 1
            else:
                empty += 1
        n = len(no_match_examples)
        result["no_match"] = {
            "n": n,
            "empty_result_rate": empty / n if n else 0.0,
            "any_hit_rate": with_hits / n if n else 0.0,
            "note": (
                "no_match queries have no relevant golden job; they are excluded "
                "from nDCG/RR/Recall aggregates. any_hit_rate is informational only "
                "when the index contains more than the golden set."
            ),
        }

    return result


def per_query_metrics(
    qid: str,
    expected_job_id: str | None,
    ranked_job_ids: list[str],
    measures: list | None = None,
) -> dict[str, float] | None:
    """Single-query metrics for LangSmith evaluators. Returns None for no_match."""
    if expected_job_id is None:
        return None
    measures = measures or [nDCG @ 10, nDCG @ 20, RR, R @ 10]
    qrels = {qid: {expected_job_id: 1}}
    run = ranked_ids_to_run(qid, ranked_job_ids)
    raw = ir_measures.calc_aggregate(measures, qrels, run)
    return _to_friendly(raw)


def format_metrics(report: dict[str, Any], indent: int = 0) -> str:
    """Pretty-print a compute_metrics_by_style report."""
    pad = "  " * indent
    lines: list[str] = []
    overall = report.get("overall", {})
    lines.append(f"{pad}overall (n_matching={report.get('n_matching', 0)}):")
    for key in ("nDCG@10", "nDCG@20", "RR", "Recall@10", "Recall@20"):
        if key in overall:
            lines.append(f"{pad}  {key}: {overall[key]:.4f}")

    by_style = report.get("by_style") or {}
    if by_style:
        lines.append(f"{pad}by_style:")
        for style, scores in by_style.items():
            n = scores.get("n", "?")
            lines.append(f"{pad}  [{style}] n={n}")
            for key in ("nDCG@10", "nDCG@20", "RR", "Recall@10", "Recall@20"):
                if key in scores:
                    lines.append(f"{pad}    {key}: {scores[key]:.4f}")

    no_match = report.get("no_match") or {}
    if no_match:
        lines.append(
            f"{pad}no_match (n={no_match.get('n', 0)}): "
            f"empty_result_rate={no_match.get('empty_result_rate', 0):.4f}, "
            f"any_hit_rate={no_match.get('any_hit_rate', 0):.4f}"
        )
    return "\n".join(lines)
