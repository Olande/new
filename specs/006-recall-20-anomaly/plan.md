# Investigation Plan: Recall@20 Metric Anomaly

**Branch**: `006-recall-20-anomaly` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-recall-20-anomaly/spec.md`

## Summary

Systematically identify why Recall@20 is consistently 0 despite nDCG@10 and MRR being high after Optuna tuning. The investigation traces the metric pipeline from dataset through metric computation, validates each transformation, and identifies the root cause — without modifying retrieval behavior.

## Technical Context

**Language/Version**: Python 3.13+

**Primary Dependencies**: `ir_measures` (metric computation), LangSmith (dataset/evaluators), SQLAlchemy (DB queries)

**Storage**: PostgreSQL 16 with pgvector — stores job data; IDs are UUID primary keys

**Testing**: `pytest` — existing evaluation tests

**Target Platform**: N/A (investigation only)

**Project Type**: FastAPI web service with offline evaluation CLI

**Performance Goals**: N/A

**Constraints**: No retrieval changes. No search parameter tuning. No ranking logic changes. Investigation only.

**Scale/Scope**: ~50 evaluation examples, single evaluation dataset, 5 metric measures (nDCG@10/20, RR, R@10/20)

## Constitution Check

*GATE passed — no violations.*

| Principle | Relevance |
|-----------|-----------|
| **III. Rigorous Testing Discipline** | Investigation validates evaluation correctness — a prerequisite for trusting any test or metric result |
| **VII. Declarative Evaluation Standards** | Investigation ensures evaluation framework produces correct metrics before any optimization decisions are made |
| **VIII. Simplicity & Minimalist Architecture** | Fix must be minimal — correct the failure point without adding new abstractions |

## Investigation Architecture

### Phase 0: Instrument and Reproduce

Add per-query diagnostic output to the offline evaluation path and confirm the anomaly is reproducible.

### Phase 1: Trace Backward from Metric Output

Starting at `compute_aggregate_metrics`, verify each input:
1. `measures` list includes `R @ 20`
2. `run` dict contains ranked job IDs for each query
3. `qrels` dict contains expected job ID for each query
4. Keys in `run` match keys in `qrels`

### Phase 2: Trace Forward from Dataset

Starting at `_load_examples`:
1. Verify `expected_job_id_of` returns correct values
2. Verify `_collect_rankings` produces ranked IDs
3. Compare expected vs. ranked ID formats at each step
4. Check `build_qrels_and_run_from_rankings` intermediate values

### Phase 3: Isolate and Fix

Based on findings, apply minimal correction to the evaluation pipeline.

### Phase 4: Verify

Re-run evaluation, confirm Recall@20 is internally consistent with nDCG@10 and MRR.

## Project Structure

### Documentation (this feature)

```text
specs/006-recall-20-anomaly/
├── plan.md              # This file — investigation strategy
├── research.md          # Phase 0 — pipeline mapping and hypotheses
├── data-model.md        # Phase 1 — metric data entities
├── quickstart.md        # Phase 1 — diagnostic run guide
├── checklists/
│   └── requirements.md  # Spec quality checklist
```

### Source Code (relevant paths)

```text
app/evaluation/
├── metrics.py           # Metric computation (build_qrels_and_run_from_rankings,
│                        #   compute_aggregate_metrics, per_query_metrics,
│                        #   expected_job_id_of, MEASURES, MEASURE_KEYS)
├── run_local.py         # Offline evaluation CLI (_collect_rankings, _evaluate_once)
├── run_eval.py          # LangSmith evaluator path (score(), metrics_for())
├── search.py            # Search execution layer (SearchParams, precompute_query_embeddings)
└── constants.py         # MATCHING_STYLES, NO_MATCH_STYLE
```

## Investigation Steps

### Step 1: Verify MEASURE KEYS Include R@20

Check that `R @ 20` is in the `MEASURES` list and `MEASURE_KEYS` maps it correctly.

### Step 2: Reproduce with Per-Query Diagnostics

Add temporary diagnostic output to `build_qrels_and_run_from_rankings` and `compute_aggregate_metrics` to print per-query intermediate values for a single trial.

### Step 3: Verify `build_qrels_and_run_from_rankings` Output

For each query, inspect:
- `qrels[qid]` keys and values
- `run[qid]` keys and values
- Whether expected job ID from qrels exists in run dict keys
- Whether skipped list is correctly computed (no false positives)

### Step 4: Verify `expected_job_id_of` Output

Check raw values from LangSmith:
- What type is `example.outputs["expected_job_id"]`?
- Does `str(raw)` produce hyphens or not?
- Compare with database-stored format via `str(r["id"])`

### Step 5: Verify `_collect_rankings` Output

Check that ranked IDs from the database are in the same string format as expected IDs.

### Step 6: Apply Fix

Based on findings, apply minimal correction (likely identifier normalization).

### Step 7: Verify Fix

Re-run full evaluation with diagnostics confirming:
- Expected job IDs match ranked IDs
- Recall@20 is non-zero for queries where expected job is in top 20
- nDCG@10, MRR, Recall@20 are internally consistent

## Verification

| Check | How | Expected |
|-------|-----|----------|
| MEASURES includes R@20 | Print `MEASURES` and `MEASURE_KEYS` | `R @ 20` is present |
| Expected ID equals ranked ID | Compare qrels key to run key per query | Exact string match for matching queries |
| Per-query diagnostics | Run offline eval with diagnostics enabled | Shows expected vs. ranked IDs |
| Recall@20 > 0 after fix | Run full evaluation | At least 1 query shows Recall>0 |
| nDCG/MRR unchanged after fix | Compare before/after | Same values (fix only affects Recall) |
| No retrieval code changed | `git diff app/retrieval/` | Empty diff |

## Root Cause Hypotheses (Ordered by Likelihood)

| # | Hypothesis | Test | Quick Check |
|---|-----------|------|-------------|
| 1 | UUID format mismatch (hyphenated vs. non-hyphenated) between LangSmith and DB | Compare expected_job_id string with str(r["id"]) | Print both for one query |
| 2 | Int vs. string ID type mismatch | Check type of raw expected_job_id from LangSmith | `type(example.outputs["expected_job_id"])` |
| 3 | Ranking dict key re-str()-ing causes corruption | Check `_collect_rankings` output before and after `build_qrels_and_run_from_rankings` | Compare `rankings[qid]` keys with `run[qid]` keys |
| 4 | `is_matching_example` filters out all matching queries | Print is_matching_example result per example | Count skipped vs. included |
| 5 | MEASURES list is overridden somewhere | Trace all calls to `compute_aggregate_metrics` | Verify default MEASURES is used |

## Rollback

No retrieval or ranking changes are made. If the diagnostic or fix introduces issues, revert the affected evaluation files only.
