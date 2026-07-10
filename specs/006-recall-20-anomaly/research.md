# Research: Recall@20 Metric Anomaly

## Pipeline Mapping

The evaluation metric pipeline was traced through the codebase:

```
Dataset (LangSmith)
  │
  ├─ _load_examples()                         → list[Example]
  │
  ├─ expected_job_id_of(example)              → str | None
  │    Reads example.outputs["expected_job_id"]
  │    Returns str(raw) or None if empty/"none"
  │
  ├─ _collect_rankings(examples, embeddings)  → dict[qid, dict[job_id, score]]
  │    Opens DB session
  │    For each example:
  │      search_jobs_with_embedding(db, query, embedding, params) → rows
  │      rankings[qid] = {str(r["id"]): float(r["rrf_score"]) for r in rows}
  │
  ├─ build_qrels_and_run_from_rankings(examples, rankings)
  │    For each example:
  │      if not is_matching_example → skip
  │      expected = expected_job_id_of(example)
  │      qrels[qid] = {expected: 1}
  │      run[qid] = {str(k): float(v) for k, v in ranking.items()}  # dict path
  │             or {str(job_id): score for rank, job_id in enumerate(ranking)}  # list path
  │    Returns (qrels, run, skipped)
  │
  ├─ compute_aggregate_metrics(qrels, run, measures)
  │    ir_measures.calc_aggregate(measures, qrels, run)
  │    → {nDCG@10: ..., nDCG@20: ..., RR: ..., Recall@10: ..., Recall@20: ...}
  │
  └─ to_friendly(raw) → dict[str, float]
       Maps ir_measures objects to string keys
```

## Identifier Flow

```
Expected job ID (from LangSmith example.outputs)
  │  Format: str(raw) — depends on how LangSmith stores it
  │
  ▼
qrels[qid] = {expected: 1}
  │  Keys are strings
  │
  ▼
ir_measures.calc_aggregate(measures, qrels, run)
  │  Matches qrels[query][doc_id] ↔ run[query][doc_id]
  │  If doc_id strings don't match → metric is 0 for that query
  │
  ▼
Result: nDCG@10, nDCG@20, RR, R@10, R@20
```

## Key Suspect: Identifier Format Discrepancy

The most likely root cause is a **string format mismatch** between the expected job ID and the ranked job IDs:

| Source | Format | Example |
|--------|--------|---------|
| `expected_job_id_of()` | `str(raw)` — LangSmith value | Could be hex, int, or UUID |
| `_collect_rankings` keys | `str(r["id"])` — PostgreSQL value | `"550e8400-e29b-41d4-a716-446655440000"` (hyphenated UUID) |

**If LangSmith stores UUIDs as hex without hyphens** (e.g., `550e8400e29b41d4a716446655440000`), while PostgreSQL returns them with hyphens (`550e8400-e29b-41d4-a716-446655440000`), then:
- `ir_measures` never finds a match between qrels and run
- All metric values (nDCG, RR, Recall) would be 0 — **but user reports nDCG and MRR are high**

This suggests the mismatch is more nuanced, or there is a second bug in how some metrics are computed.

## Alternative Hypotheses

| Hypothesis | Explanation | Predicts |
|-----------|-------------|----------|
| **H1: Identifier format mismatch** | Expected ID and ranked ID string formats differ | All metrics 0 → inconsistent with observations |
| **H2: Recall@20 measure is wrong** | `R @ 20` in ir_measures behaves differently than expected | nDCG works, Recall broken |
| **H3: Ranking format differs per path** | `_collect_rankings` dict vs list path produces different key types | Some queries work, others don't |
| **H4: Dataset has no_match majority** | Most examples are no_match, only few matching examples drive nDCG | Recall aggregated over few queries |
| **H5: Metrics computed on different subsets** | nDCG/MRR from one pipeline, Recall from another | Need to verify all metrics from same qrels/run |
| **H6: MEASURES list excludes R@20** | If `measures` parameter overrides `MEASURES` | R@20 never computed |

## LangSmith Evaluator Path (run_eval.py)

The LangSmith evaluators (`score()`, `ndcg_at_10()`, etc.) use `metrics_for()` → `per_query_metrics()` which constructs qrels/run inline — this is a separate code path from the offline evaluation. If the bug is in that path, it would affect LangSmith-reported metrics but not offline evaluation.

## Decision

**Approach**: Systematic debug-by-elimination starting from the metric computation output and working backward through the pipeline.

**Rationale**: The symptom (Recall=0, nDCG>0) is mathematically suspicious. Starting at the metric function and verifying inputs at each step backward is the most reliable way to find the exact failure point.

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Blind fix (add UUID normalization) | Would patch symptom without confirming root cause — could mask multiple bugs |
| Add comprehensive logging only | Passive — need active diagnostic instrumentation to trigger the failure |
| Review ir_measures source | The library is well-tested; the bug is almost certainly in how we call it |
