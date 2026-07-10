import argparse
import asyncio
import json
import logging
import sys

from dotenv import load_dotenv
from langsmith import Client
from loguru import logger

from app.core.db.base import async_session
from app.evaluation.metrics import (
    compute_metrics_by_style,
    expected_job_id_of,
    format_metrics,
    query_style_of,
)
from app.evaluation.search import (
    DEFAULT_SEARCH_PARAMS,
    RETRIEVAL_DATASET,
    SearchParams,
    precompute_query_embeddings,
    search_jobs_with_embedding,
)

_ = load_dotenv()


async def collect_rankings(
    examples: list,
    query_embeddings: dict[str, list[float]],
    params: SearchParams,
) -> dict[str, dict[str, float]]:
    rankings: dict[str, dict[str, float]] = {}
    async with async_session() as db:
        for example in examples:
            qid = str(example.id)
            query_text = example.inputs["query"]
            embedding = query_embeddings[query_text]
            try:
                rows = await search_jobs_with_embedding(
                    db, query_text, embedding, params
                )
                rankings[qid] = {str(r["id"]): float(r["rrf_score"]) for r in rows}
            except Exception:
                logger.exception("search failed for query_id=%s", qid)
                rankings[qid] = {}
    return rankings


async def evaluate_once(
    examples: list,
    query_embeddings: dict[str, list[float]],
    params: SearchParams,
) -> dict:
    rankings = await collect_rankings(examples, query_embeddings, params)
    report = compute_metrics_by_style(examples, rankings)
    report["params"] = params.as_dict()
    return report


async def grid_search(
    examples: list,
    query_embeddings: dict[str, list[float]],
    thresholds: list[float] | None = None,
) -> dict:
    thresholds = thresholds or [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    best_ndcg = -1.0
    best_rr = -1.0
    best_report: dict | None = None

    for bm_w in [i / 10 for i in range(11)]:
        vec_w = round(1.0 - bm_w, 2)
        for threshold in thresholds:
            params = SearchParams(
                bm25_weight=bm_w,
                vector_weight=vec_w,
                cosine_distance_threshold=threshold,
            )
            report = await evaluate_once(examples, query_embeddings, params)
            ndcg = report["overall"].get("nDCG@10", 0.0)
            rr = report["overall"].get("RR", 0.0)
            if ndcg > best_ndcg or (ndcg == best_ndcg and rr > best_rr):
                best_ndcg = ndcg
                best_rr = rr
                best_report = report
                print(
                    f"NEW BEST: bm25={bm_w:.2f}, vector={vec_w:.2f}, "
                    f"threshold={threshold:.2f} -> "
                    f"nDCG@10={ndcg:.4f}, RR={rr:.4f}"
                )

    assert best_report is not None
    return best_report


def print_per_query(examples: list, rankings: dict[str, dict[str, float]]) -> None:
    from app.evaluation.metrics import per_query_metrics

    print("\n--- per-query ---")
    for example in examples:
        qid = str(example.id)
        style = query_style_of(example)
        expected = expected_job_id_of(example)
        ranking = rankings.get(qid, {})
        # preserve score order
        ordered = [
            doc_id
            for doc_id, _ in sorted(ranking.items(), key=lambda kv: kv[1], reverse=True)
        ]
        query = example.inputs.get("query", "")
        if expected is None:
            print(f"[{style}] no_match  hits={len(ordered)}  q={query!r}")
            continue
        metrics = per_query_metrics(qid, expected, ordered) or {}
        rank = ordered.index(expected) + 1 if expected in ordered else None
        print(
            f"[{style}] rank={rank!s:>4}  nDCG@10={metrics.get('nDCG@10', 0):.3f}  "
            f"RR={metrics.get('RR', 0):.3f}  q={query!r}"
        )


async def async_main(args: argparse.Namespace) -> int:
    print(f"Fetching examples from LangSmith dataset '{RETRIEVAL_DATASET}'...")
    client = Client()
    examples = list(client.list_examples(dataset_name=RETRIEVAL_DATASET))
    if not examples:
        print(f"No examples found in {RETRIEVAL_DATASET}.", file=sys.stderr)
        return 1

    print(f"Loaded {len(examples)} examples. Pre-computing query embeddings...")
    queries = [ex.inputs["query"] for ex in examples]
    query_embeddings = await precompute_query_embeddings(queries)

    if args.grid:
        print("Starting grid search over hyper-parameters...")
        report = await grid_search(examples, query_embeddings)
        print("\n--- OPTIMAL HYPER-PARAMETERS ---")
    else:
        params = SearchParams(
            bm25_weight=args.bm25,
            vector_weight=args.vector,
            cosine_distance_threshold=args.threshold,
            result_limit=args.limit,
        )
        print(f"Evaluating with {params.as_dict()} ...")
        report = await evaluate_once(examples, query_embeddings, params)

    print(format_metrics(report))
    print(f"\nparams: {json.dumps(report.get('params', {}), indent=2)}")

    if args.per_query and not args.grid:
        params = SearchParams(
            bm25_weight=args.bm25,
            vector_weight=args.vector,
            cosine_distance_threshold=args.threshold,
            result_limit=args.limit,
        )
        rankings = await collect_rankings(examples, query_embeddings, params)
        print_per_query(examples, rankings)

    if args.json:
        # Make JSON-serializable copy
        print(json.dumps(report, indent=2, default=str))

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Offline hybrid-search IR evaluation for CareerPilot"
    )
    p.add_argument(
        "--bm25",
        type=float,
        default=DEFAULT_SEARCH_PARAMS.bm25_weight,
        help="BM25 / lexical weight (default: production 0.1)",
    )
    p.add_argument(
        "--vector",
        type=float,
        default=DEFAULT_SEARCH_PARAMS.vector_weight,
        help="Vector weight (default: production 0.9)",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_SEARCH_PARAMS.cosine_distance_threshold,
        help="Cosine distance threshold (default: production 0.5)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_SEARCH_PARAMS.result_limit,
        help="Result limit k (default: 20)",
    )
    p.add_argument(
        "--grid",
        action="store_true",
        help="Grid-search weights (sum to 1) × thresholds; print best by nDCG@10",
    )
    p.add_argument(
        "--per-query",
        action="store_true",
        help="Print per-query rank / metrics (ignored with --grid)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Also dump the full metrics report as JSON",
    )
    return p


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
