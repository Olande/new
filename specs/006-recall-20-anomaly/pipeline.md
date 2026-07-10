# Metric Pipeline Diagram: Recall@20 Anomaly

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    LangSmith Dataset                         │
│              careerpilot-matching-eval-v2                    │
│  Example { inputs.query, outputs.expected_job_id }          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                _load_examples()                              │
│  (run_local.py:101)  →  list[Example]                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ├──────────────────────────────────┐
                           │                                  │
                           ▼                                  ▼
┌──────────────────────────────────────────┐    ┌──────────────────────────────┐
│  expected_job_id_of(example)             │    │  _collect_rankings()          │
│  (metrics.py:41)                         │    │  (run_local.py:37)            │
│  → str(raw) or None                      │    │  → search_jobs_with_embedding │
│    Format: hyphenated UUID string        │    │  → {str(r["id"]): rrf_score}  │
│    e.g. "e183b24e-b7af-59df-b596-..."    │    │    Format: hyphenated UUID    │
└──────────────────┬───────────────────────┘    │    e.g. "e183b24e-..."         │
                   │                            └──────────────┬───────────────┘
                   │                                           │
                   ▼                                           ▼
┌─────────────────────────────────────────────────────────────┐
│            build_qrels_and_run_from_rankings()               │
│                   (metrics.py:76)                            │
│                                                              │
│  For each example:                                           │
│    1. is_matching_example? → skip if no_match               │
│    2. qrels[qid] = {expected_job_id: 1}                     │
│    3. run[qid] = {ranked_job_id: score}                     │
│                                                              │
│  *** IDENTIFIER MATCHING HAPPENS HERE ***                   │
│  qrels[qid].keys() vs. run[qid].keys()                      │
│  Must be exact string match for ir_measures to work          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            compute_aggregate_metrics()                       │
│                   (metrics.py:119)                           │
│                                                              │
│  measures = MEASURES = [nDCG@10, nDCG@20, RR, R@10, R@20]  │
│  raw = ir_measures.calc_aggregate(measures, qrels, run)     │
│  return to_friendly(raw)                                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  METRICS OUTPUT                              │
│  { "nDCG@10": 0.8606, "nDCG@20": 0.8606,                   │
│    "RR": 0.8529, "Recall@10": 0.8824,                      │
│    "Recall@20": 0.8824 }                                    │
└─────────────────────────────────────────────────────────────┘
```

## LangSmith Evaluator Path (Secondary)

```
recall_at_20  →  score()  →  metrics_for()  →  metrics_for_ranked()
                                                      │
                                                      ▼
                                            per_query_metrics()
                                            (metrics.py:220)
                                                      │
                          *** BUG WAS HERE ***        │
                          Line 229 default measures:  │
                          [nDCG@10, nDCG@20, RR,     │
                           R@10]                     │
                          ← R @ 20 MISSING!          │
                                                      ▼
                                            Result dict has no
                                            "Recall@20" key
                                                      │
                                                      ▼
                                            score() calls
                                            m.get("Recall@20", 0.0)
                                            → always returns 0.0
```

## Offline Evaluation Path (run_local.py) — No Bug

```
_evaluate_once() → compute_metrics_by_style()
                       → build_qrels_and_run_from_rankings() ✓ IDs match
                       → compute_aggregate_metrics()
                           → MEASURES includes R @ 20 ✓
                           → ir_measures produces R@20 correctly ✓
```

## Fix Applied

**File**: `app/evaluation/metrics.py`, line 229
**Change**: Added `R @ 20` to `per_query_metrics()` default measures:

```python
# Before (broken):
measures = measures or [nDCG @ 10, nDCG @ 20, RR, R @ 10]

# After (fixed):
measures = measures or [nDCG @ 10, nDCG @ 20, RR, R @ 10, R @ 20]
```

## Summary

| Path | Status | Reason |
|------|--------|--------|
| Offline eval (`run_local.py`) | ✅ Always worked | Uses `compute_aggregate_metrics` with full `MEASURES` |
| LangSmith eval (`run_eval.py`) | ❌ Was broken | `per_query_metrics` default excluded `R@20` |
| After fix | ✅ Both paths correct | `R @ 20` now in `per_query_metrics` defaults |
