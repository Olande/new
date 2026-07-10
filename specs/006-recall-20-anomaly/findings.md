# Findings: Recall@20 Metric Anomaly

**Date**: 2026-07-10
**Feature**: `006-recall-20-anomaly`
**Status**: Resolved

---

## Symptom

Recall@20 was reported as consistently 0 despite nDCG@10 (~0.86) and MRR (~0.85) being high after Optuna hyperparameter tuning. This suggested a systematic bug rather than a data quality issue, since it's mathematically improbable for a retrieval system to have high nDCG and zero Recall simultaneously.

## Investigation Method

**Backward trace**: Starting at the metric output and verifying each input stage in reverse order.

1. **Verify MEASURES** → `R @ 20` present in `MEASURES` list and `MEASURE_KEYS` mapping ✓
2. **Verify call sites** → Both `compute_aggregate_metrics` call sites use default `MEASURES` ✓
3. **Check ID format consistency** → LangSmith `expected_job_id` (type `str`, hyphenated UUID) vs. PostgreSQL `str(r["id"])` (type `str`, hyphenated UUID) → **exact match for all 17 examples** ✓
4. **Verify search returns expected jobs** → 15/17 expected job IDs found in ranked results ✓
5. **Add diagnostic logging** to `build_qrels_and_run_from_rankings()` and `compute_aggregate_metrics()`
6. **Run full evaluation** with diagnostics

## Root Cause

The bug was in `per_query_metrics()` at line 229 of `app/evaluation/metrics.py`:

```python
# Default measures EXCLUDED R @ 20:
measures = measures or [nDCG @ 10, nDCG @ 20, RR, R @ 10]  # ← R @ 20 MISSING!
```

This default is used by the LangSmith evaluator chain:

```
recall_at_20 → score() → metrics_for() → metrics_for_ranked() → per_query_metrics()
```

Since `per_query_metrics` never computed `R @ 20`, the result dict (`m`) did not contain the `"Recall@20"` key. Then `score()` called `m.get("Recall@20", 0.0)`, which returned `0.0` because the key was absent.

### Key Detail

The **offline evaluation path** (`run_local.py`) was **NOT affected** because it uses `compute_aggregate_metrics()` which defaults to the full `MEASURES` list including `R @ 20`. Only the LangSmith evaluator path via `per_query_metrics()` had the bug.

## Evidence

Before any diagnostics were added, running the offline evaluation produced:

```
overall (n_matching=17):
  nDCG@10: 0.8606
  nDCG@20: 0.8606
  RR: 0.8529
  Recall@10: 0.8824
  Recall@20: 0.8824    ← Was NEVER actually zero in this path!
```

Diagnostic logging confirmed `ir_measures.calc_aggregate` returns correct `R@20` values:
```
DIAG: raw_results={'R@10': 0.882, 'R@20': 0.882, 'nDCG@20': 0.861, 'RR': 0.853, 'nDCG@10': 0.861}
```

## Fix Applied

**File**: `app/evaluation/metrics.py`, line 229
**Change**: One-line addition of `R @ 20` to `per_query_metrics` default measures:

```python
# Before:
measures = measures or [nDCG @ 10, nDCG @ 20, RR, R @ 10]

# After:
measures = measures or [nDCG @ 10, nDCG @ 20, RR, R @ 10, R @ 20]
```

## Verification

### Before fix: `per_query_metrics` excluded R@20
- LangSmith `recall_at_20` evaluator always returned 0.0
- Offline evaluation was correct (Recall@20 = 0.8824)

### After fix: Both paths produce correct metrics
- Offline evaluation: Recall@20 = 0.8824 **(unchanged)** ✓
- LangSmith evaluator path: now correctly computes R@20 ✓
- nDCG@10: 0.8606 **(unchanged)** ✓
- RR: 0.8529 **(unchanged)** ✓
- Per-query consistency: 0 inconsistencies across 17 matching queries ✓

### Hypotheses Ruled Out

| Hypothesis | Status | Evidence |
|-----------|--------|----------|
| UUID format mismatch (hyphenated vs. non-hyphenated) | ❌ Ruled out | Both sides produce identical hyphenated UUID strings |
| Int vs. string ID type mismatch | ❌ Ruled out | Both sides are type `str` |
| Ranking dict key corruption | ❌ Ruled out | `str(r["id"])` → uuid → `str()` → consistent format |
| is_matching_example skips all queries | ❌ Ruled out | Only 3/20 skipped (correctly — no_match style) |
| MEASURES list overridden somewhere | ❌ Ruled out | All call sites use default MEASURES |
| **per_query_metrics default excludes R@20** | ✅ **Root cause** | Confirmed by diagnostic logging and code inspection |

### Changed Files

| File | Change |
|------|--------|
| `app/evaluation/metrics.py` (line 229) | Added `R @ 20` to `per_query_metrics` default measures |
| `app/evaluation/metrics.py` (lines 87, 104, 127) | Replaced temporary `print()` diagnostics with permanent `logger.debug()` |

### Unchanged Files

| File | Constraint (SC-005) |
|------|---------------------|
| `app/retrieval/` | ✅ No changes — all changes are in evaluation code |
| `app/evaluation/search.py` | ✅ No changes |
| `app/evaluation/run_local.py` | ✅ No changes |
| `app/evaluation/constants.py` | ✅ No changes |
| `app/evaluation/run_eval.py` | ✅ No changes |

## Lessons Learned

1. **Default argument mismatch**: `per_query_metrics()` had a different default measures list from `MEASURES`, causing inconsistent behavior between two code paths that should produce equivalent results.
2. **Silent fallback**: `.get(key, 0.0)` masked the missing key — if the key doesn't exist, it silently returns the default rather than raising an error. Consider using explicit key access or logging when a requested metric key is absent.
3. **Diagnostic-first investigation**: The backward-trace approach (output → input) was effective in narrowing down the failure point. The format mismatch hypothesis was the most natural guess but turned out to be wrong — the real bug was a missing measure in a separate code path.
