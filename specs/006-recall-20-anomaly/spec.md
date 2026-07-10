# Feature Specification: Recall@20 Metric Anomaly Investigation

**Feature Branch**: `006-recall-20-anomaly`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "Investigate why Recall@20 remains consistently 0 despite nDCG@10 and MRR being high — determine whether the metric, the data, or the pipeline is at fault."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Diagnose the root cause of Recall@20=0 (Priority: P1)

As a developer investigating evaluation metrics, I want to trace the full pipeline from dataset example through metric computation to identify why Recall@20 is stuck at zero, so I can determine whether the bug is in data labels, identifier matching, metric logic, or ranking inputs.

**Why this priority**: Until the root cause is found, the metric cannot be trusted and all retrieval evaluation results are unreliable.

**Independent Test**: Run the existing evaluation on any single example where Recall@20=0 but nDCG@10>0 — the diagnostic output must show the exact mismatch point (expected job ID vs. ranked IDs vs. qrels vs. metric computation).

**Acceptance Scenarios**:

1. **Given** an evaluation run where Recall@20=0 and nDCG@10>0, **When** per-query diagnostics are printed, **Then** they show query text, expected job ID, top-20 returned job IDs, per-query nDCG@10, MRR, and Recall@20.
2. **Given** a per-query diagnostic showing Recall@20=0, **When** the expected job ID is compared to the ranked IDs, **Then** either the expected ID is absent from the ranked set or the comparison failed due to format mismatch.
3. **Given** a suspect metric computation path, **When** `build_qrels_and_run_from_rankings` intermediate values are logged, **Then** the qrels dict, run dict, and skipped list show whether the example was properly included.

---

### User Story 2 — Fix the detected failure point and verify (Priority: P2)

As a developer, I want to apply the minimal correction once the root cause is identified, so that Recall@20 produces consistent results with nDCG@10 and MRR.

**Why this priority**: A fix is valueless without understanding; diagnosis must precede correction.

**Independent Test**: After the fix, running the same evaluation that previously showed Recall@20=0 must produce a non-zero Recall@20 that is consistent with nDCG@10 and MRR values.

**Acceptance Scenarios**:

1. **Given** the root cause identified in US1, **When** the fix is applied, **Then** no retrieval logic or search parameters are changed.
2. **Given** the fix applied, **When** the full evaluation suite is run, **Then** Recall@20 is consistently non-zero for queries where expected jobs appear in the ranked results.

---

### User Story 3 — Document the metric pipeline and failure mode (Priority: P3)

As a team member reviewing the evaluation system, I want a clear diagram and written explanation of the metric data flow and the discovered bug, so that future contributors understand the pipeline and avoid regressions.

**Why this priority**: Documentation prevents recurrence and aids onboarding.

**Independent Test**: A new team member can read the pipeline diagram and trace a single example through all stages without ambiguity.

**Acceptance Scenarios**:

1. **Given** the pipeline diagram, **When** following it for any example, **Then** each stage shows the exact data transformation at that step.
2. **Given** the failure-mode documentation, **When** a similar identifier mismatch occurs in the future, **Then** the troubleshooting steps point to the likely cause.

---

### Edge Cases

- What happens if a query has no matching expected job ID (no_match)? It should be excluded from Recall computation — verify this exclusion does not accidentally drop valid queries.
- What if the expected job ID exists in the dataset but not in the indexed corpus? Recall should be 0 for that query, but other metrics would also be 0.
- What if the expected job ID appears in ranked results but with a different format (UUID string vs. int vs. hyphenated)? The metric comparison would fail silently — this is a key suspect.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The investigation MUST trace a failing example through the full pipeline: dataset example → `expected_job_id_of()` → `build_qrels_and_run_from_rankings()` → `compute_aggregate_metrics()` → final metric output.
- **FR-002**: Per-query diagnostics MUST print for each query: query text, expected job ID, ranked job IDs (top 20), per-query nDCG@10, MRR, and Recall@20.
- **FR-003**: The qrels and run dicts produced by `build_qrels_and_run_from_rankings` MUST be inspectable to verify the expected job ID is present in qrels and the ranked job IDs are present in the run dict.
- **FR-004**: Identifier comparisons (expected job ID vs. ranked job IDs) MUST be checked for format consistency: UUID string formats, integer vs. string types, hyphens, leading/trailing whitespace.
- **FR-005**: Any fix MUST change only evaluation logic or diagnostics — no retrieval, search parameter, or ranking changes are permitted.
- **FR-006**: After the fix, the evaluation MUST produce non-zero Recall@20 for at least one query where the expected job appears in the top 20 results.

### Key Entities

- **Dataset example**: LangSmith Example with `inputs.query` and `outputs.expected_job_id`
- **Expected job ID**: The gold-standard job identifier for a given query
- **Ranked results**: List of job IDs returned by hybrid search, ordered by RRF score
- **qrels dict**: `{qid: {expected_job_id: 1}}` — relevance judgments
- **run dict**: `{qid: {ranked_job_id: score}}` — retrieval output
- **Metric measures**: `nDCG@10`, `nDCG@20`, `RR`, `R@10`, `R@20` — computed by `ir_measures`

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Root cause identified and documented with evidence (specific code path, variable values, and comparison failure).
- **SC-002**: Metric pipeline diagram showing data flow from dataset to metric output, with the failure point clearly marked.
- **SC-003**: After fix, at least one query that previously showed Recall@20=0 now shows Recall@20>0.
- **SC-004**: After fix, nDCG@10, MRR, and Recall@20 values are internally consistent (no query shows high nDCG but zero Recall when the expected job is in the ranked set).
- **SC-005**: All changes are limited to evaluation/diagnostic code — retrieval behavior is unchanged.

## Assumptions

- **Scope boundary**: No changes to `app/retrieval/`, `app/core/jdl/`, or search parameter defaults.
- **Existing evaluation utilities**: `_collect_rankings`, `_evaluate_once`, `build_qrels_and_run_from_rankings`, and `compute_metrics_by_style` are the correct pipeline to trace.
- **Expected job ID source**: `expected_job_id_of(example)` extracts the correct value from LangSmith example outputs.
- **Metric library**: `ir_measures` is correctly computing metrics given proper qrels and run inputs — the bug is likely in how qrels/run are constructed or how identifiers match.
- **Test environment**: The existing evaluation dataset (`careerpilot-matching-eval-v2`) and `_load_examples()` function provide the test data.
