# Quickstart: Recall@20 Metric Anomaly Investigation

## Prerequisites

- Python 3.13+
- `uv` package manager
- `.venv/` with all dependencies installed (`uv sync`)
- LangSmith API key configured (for dataset access in offline evaluation)
- PostgreSQL running with indexed job data

## Quick Diagnostic Run

Run the offline evaluation with per-query diagnostics to reproduce and inspect the anomaly:

```bash
uv run python -c "
from app.evaluation.run_local import _load_examples, _collect_rankings, _evaluate_once
from app.evaluation.search import precompute_query_embeddings, DEFAULT_SEARCH_PARAMS
from app.evaluation.metrics import build_qrels_and_run_from_rankings, MEASURES, MEASURE_KEYS

import asyncio

async def diagnose():
    examples = _load_examples()
    queries = [ex.inputs['query'] for ex in examples]
    embeddings = await precompute_query_embeddings(queries)
    rankings = await _collect_rankings(examples, embeddings, DEFAULT_SEARCH_PARAMS)

    qrels, run, skipped = build_qrels_and_run_from_rankings(examples, rankings)

    print(f'=== DIAGNOSTICS ===')
    print(f'Total examples: {len(examples)}')
    print(f'Qrels queries: {len(qrels)}')
    print(f'Run queries: {len(run)}')
    print(f'Skipped (no_match): {len(skipped)}')
    print(f'MEASURES: {MEASURES}')
    print(f'MEASURE_KEYS: {MEASURE_KEYS}')
    print()

    for ex in examples[:5]:  # first 5 examples
        qid = str(ex.id)
        expected = qrels.get(qid, {})
        ranked = run.get(qid, {})
        expected_str = str(expected)
        ranked_str = str(ranked)
        match = 'MATCH' if any(k in ranked for k in expected) else 'NO MATCH'
        print(f'Query: {ex.inputs[\"query\"][:60]}...')
        print(f'  QID: {qid}')
        print(f'  Expected IDs: {list(expected.keys())[:3]}')
        print(f'  Ranked IDs (top 5): {list(ranked.keys())[:5]}')
        print(f'  Expected in Ranked: {match}')
        print(f'  Skipped: {qid in skipped}')
        if not match:
            print(f'  Expected type: {[type(k).__name__ for k in expected.keys()]}')
            print(f'  Ranked types: {[type(k).__name__ for k in ranked.keys()][:5]}')
            print(f'  Expected repr: {[repr(k) for k in expected.keys()][:3]}')
            print(f'  Ranked repr: {[repr(k) for k in ranked.keys()][:3]}')
        print()

    report = await _evaluate_once(examples, embeddings, DEFAULT_SEARCH_PARAMS)
    print(f'=== OVERALL METRICS ===')
    for k, v in report.get('overall', {}).items():
        print(f'  {k}: {v:.4f}')
    print(f'n_matching: {report.get(\"n_matching\")}')
    print(f'n_skipped_no_match: {report.get(\"n_skipped_no_match\")}')

asyncio.run(diagnose())
"
```

## Per-Query Metric Diagnostics

To compute per-query metrics and compare nDCG vs. Recall:

```bash
uv run python -c "
from app.evaluation.run_local import _load_examples, _collect_rankings
from app.evaluation.search import precompute_query_embeddings, DEFAULT_SEARCH_PARAMS
from app.evaluation.metrics import (
    build_qrels_and_run_from_rankings, compute_aggregate_metrics,
    per_query_metrics, MEASURES, expected_job_id_of
)
import asyncio

async def per_query():
    examples = _load_examples()
    queries = [ex.inputs['query'] for ex in examples]
    embeddings = await precompute_query_embeddings(queries)
    rankings = await _collect_rankings(examples, embeddings, DEFAULT_SEARCH_PARAMS)
    qrels, run, skipped = build_qrels_and_run_from_rankings(examples, rankings)

    print(f'=== PER-QUERY METRICS ===')
    for ex in examples:
        qid = str(ex.id)
        if qid in skipped:
            continue
        expected = expected_job_id_of(ex)
        ranked_for_run = run.get(qid, {})
        ranked_list = list(ranked_for_run.keys())

        m = per_query_metrics(qid, expected, ranked_list)
        if m:
            print(f'Query: {ex.inputs[\"query\"][:50]}')
            print(f'  Expected: {expected}')
            print(f'  In top 20: {expected in ranked_list}')
            print(f'  nDCG@10: {m.get(\"nDCG@10\", 0):.4f}')
            print(f'  MRR: {m.get(\"RR\", 0):.4f}')
            print(f'  Recall@10: {m.get(\"Recall@10\", 0):.4f}')
            print(f'  Recall@20: {m.get(\"Recall@20\", 0) if \"Recall@20\" in m else \"N/A\"}')
            print()

asyncio.run(per_query())
"
```

## Step-by-Step Diagnostic Sequence

### 1. Verify MEASURES list

```bash
uv run python -c "from app.evaluation.metrics import MEASURES, MEASURE_KEYS; print('Measures:', MEASURES); print('Keys:', MEASURE_KEYS)"
```

Expected: Both `R @ 10` and `R @ 20` present in MEASURES; both `Recall@10` and `Recall@20` in MEASURE_KEYS.

### 2. Check expected_job_id format from LangSmith

```bash
uv run python -c "
from app.evaluation.run_local import _load_examples
exs = _load_examples()
for ex in exs[:3]:
    raw = ex.outputs.get('expected_job_id')
    print(f'raw type={type(raw).__name__} value={raw!r} str={str(raw)!r}')
"
```

This reveals whether LangSmith stores UUIDs as hex, int, or hyphenated strings.

### 3. Compare with DB ID format

```bash
uv run python -c "
import asyncio, uuid
from app.core.db.base import async_session
from sqlalchemy import select, text

async def check_db_id():
    async with async_session() as db:
        row = (await db.execute(text('SELECT id FROM jobs LIMIT 1'))).one_or_none()
        if row:
            raw = row[0]
            print(f'DB raw type={type(raw).__name__} value={raw!r} str={str(raw)!r}')

asyncio.run(check_db_id())
"
```

### 4. Verify `build_qrels_and_run_from_rankings` intermediate values

Add temporary print statements to `build_qrels_and_run_from_rankings` in `app/evaluation/metrics.py` and re-run the quick diagnostic.

## Validation After Fix

### Check 1 — Recall@20 > 0

Re-run the full offline evaluation and print the `overall` metrics:

```bash
uv run python -m app.evaluation.run_local
```

### Check 2 — Internal Consistency

No query should show nDCG@10 > 0.5 with Recall@20 = 0 when the expected job is in the ranked results. Run the per-query diagnostic above and verify.

### Check 3 — No Retrieval Changes

```bash
git diff -- app/retrieval/
```

Should be empty.

## Undo Diagnostics

Remove any temporary print/logging statements added during investigation. The fix itself should be a minimal change to identifier handling.
