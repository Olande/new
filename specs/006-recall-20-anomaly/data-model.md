# Data Model: Recall@20 Metric Anomaly

This investigation does not introduce any new persistent data entities. The entities below are the conceptual data objects that flow through the metric pipeline.

## Pipeline Entities

### Dataset Example
- **Source**: LangSmith dataset (`careerpilot-matching-eval-v2`)
- **Key fields**:
  - `id`: Example ID (UUID, used as qid)
  - `inputs.query`: Query text string
  - `inputs.query_style`: Classification label (exact_terms, paraphrase, distractor, no_match)
  - `outputs.expected_job_id`: Ground-truth relevant job ID

### Expected Job ID
- **Format**: String value from `example.outputs["expected_job_id"]`
- **Source function**: `expected_job_id_of()` in `app/evaluation/metrics.py`
- **Type after extraction**: `str | None`
- **Potential issue**: The raw value from LangSmith may be UUID object, hex string, or integer — `str(raw)` conversion could differ from DB format

### Ranked Results
- **Source**: `_collect_rankings()` → `search_jobs_with_embedding()` returning DB rows
- **Key field**: `r["id"]` — PostgreSQL UUID primary key
- **Format after extraction**: `str(r["id"])` — standard Python `str()` on a UUID object produces hyphenated lowercase format

### qrels Dict
- **Structure**: `{query_id: {expected_job_id: 1}}`
- **Built by**: `build_qrels_and_run_from_rankings()` in `app/evaluation/metrics.py`
- **Used by**: `ir_measures.calc_aggregate()`

### run Dict
- **Structure**: `{query_id: {ranked_job_id: rrf_score}}`
- **Built by**: `build_qrels_and_run_from_rankings()` — two paths:
  - **Dict path**: `{str(k): float(v) for k, v in ranking.items()}`
  - **List path**: `{str(job_id): score ...}`
- **Used by**: `ir_measures.calc_aggregate()`

### Metric Measures
- **Defined in**: `app/evaluation/metrics.py` → `MEASURES`
- **Contents**: `[nDCG @ 10, nDCG @ 20, RR, R @ 10, R @ 20]`
- **Output keys**: `MEASURE_KEYS` → `{"nDCG@10", "nDCG@20", "RR", "Recall@10", "Recall@20"}`

## Identifier Flow

```
┌─────────────────────────────────────┐
│ LangSmith Example                   │
│  outputs.expected_job_id: ?         │
└──────────┬──────────────────────────┘
           │ expected_job_id_of()
           ▼
┌─────────────────────────────────────┐
│ str(expected_job_id)                │  ← Format unknown (depends on LangSmith)
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ qrels[qid] = {expected_id: 1}      │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ ir_measures.calc_aggregate(...)     │
│  Compares:                          │
│    qrels[qid].keys()                │
│    vs.                              │
│    run[qid].keys()                  │
└──────────▲──────────────────────────┘
           │
┌──────────┴──────────────────────────┐
│ run[qid] = {str(r["id"]): score}    │  ← str(UUID) produces "550e8400-e29b-..."
└─────────────────────────────────────┘
           ▲
           │ _collect_rankings()
┌──────────┴──────────────────────────┐
│ PostgreSQL row                      │
│  id: UUID primary key               │
└─────────────────────────────────────┘
```

## Validation Points

| Point | What to Validate | Expected vs. Actual |
|-------|-----------------|-------------------|
| V1 | `raw = example.outputs["expected_job_id"]` type | UUID, str, or int? |
| V2 | `str(raw)` format | Hyphenated hex vs. plain hex vs. decimal |
| V3 | `r["id"]` type from DB | UUID object |
| V4 | `str(r["id"])` format | `550e8400-e29b-41d4-a716-446655440000` |
| V5 | qrels key == run key for same document | Exact string equality |
| V6 | MEASURES list contents | R @ 20 present |
| V7 | MEASURE_KEYS mapping | `R @ 20` → `"Recall@20"` |
