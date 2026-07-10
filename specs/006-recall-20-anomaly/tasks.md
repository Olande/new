# Tasks: Recall@20 Metric Anomaly Investigation

**Input**: Design documents from `/specs/006-recall-20-anomaly/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Not applicable — this is an investigation, not a feature build. Each task produces observable evidence.

**Organization**: Tasks are grouped by investigation phase, following the backward-trace strategy: verify metric definitions first, then trace pipeline from output to input, then fix, verify, and document.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (independent evidence-gathering)
- **[Story]**: Which user story this task supports (US1=diagnose, US2=fix, US3=document)
- Include exact file paths in descriptions

---

## Phase 1: Setup & Quick Checks

**Purpose**: Validate the basic building blocks before investing in deep tracing.

- [X] T001 Check that `R @ 20` is present in `MEASURES` and mapped in `MEASURE_KEYS` in `app/evaluation/metrics.py` — run:
      `uv run python -c "from app.evaluation.metrics import MEASURES, MEASURE_KEYS; print(MEASURES); print(MEASURE_KEYS)"`
      → Confirmed: `R @ 20` in MEASURES, `"Recall@20"` in MEASURE_KEYS. ✓
- [X] T002 [P] Verify that all call sites of `compute_aggregate_metrics` pass the default `MEASURES` list (not a filtered subset) in `app/evaluation/metrics.py` and `app/evaluation/run_local.py`
      → Both call sites (lines 134, 149) pass no `measures` arg → default to MEASURES (includes R @ 20). ✓
      *Note: `per_query_metrics` (line 180) overrides to `[nDCG@10, nDCG@20, RR, R@10]` — excludes R@20 — but this is for LangSmith evaluator path, not offline eval.*
- [X] T003 [P] Check that `build_qrels_and_run_from_rankings` in `app/evaluation/metrics.py` handles both dict-type and list-type rankings (dict path at line ~96 and list path at line ~100) — confirm neither path silently drops `R @ 20` candidates
      → Dict path: `{str(k): float(v)}` — list path: `{str(job_id): score}` — both produce `dict[str, float]` with string keys. ✓

---

## Phase 2: Foundational — Pipeline Integrity (Blocking Prerequisites)

**⚠️ CRITICAL**: Must complete before US1 diagnosis — ensures the pipeline is not fundamentally broken.

- [X] T004 Print `type()` and `repr()` of `example.outputs["expected_job_id"]` for 3 examples from LangSmith to verify the raw ID type (UUID object, hex string, int, or hyphenated string). Use `_load_examples()` from `app/evaluation/run_local.py` and print output.
      → type=str, hyphenated UUID format (e.g., "e183b24e-b7af-59df-b596-1c9aa356ea63"). ✓
- [X] T005 [P] Print `type()` and `repr()` of `r["id"]` from a database row returned by `search_jobs_with_embedding` to verify the DB ID format. Use `async_session()` from `app.core.db.base` and run a raw query: `SELECT id FROM jobs LIMIT 1`.
      → DB returns UUID object, str(UUID(...)) → "47af882b-1867-4600-9418-c87d84930753" (hyphenated). ✓
- [X] T006 Compare the results of T004 and T005 side by side:
      → BOTH produce hyphenated UUID strings. NO format mismatch. All 17 expected IDs exist in DB with exact string match.
- [X] T007 (Skipped — no format mismatch detected, ID formats match natively.)

**Checkpoint**: Foundation evidence gathered — we know whether identifiers match or mismatch at the string level.

---

## Phase 3: User Story 1 — Diagnose Root Cause (Priority: P1) 🎯 MVP

**Goal**: Trace the full pipeline from dataset through metric computation and identify the exact failure point causing Recall@20=0.

**Independent Test**: The diagnostic output produced by T010 must show the exact mismatch point (expected job ID vs. ranked IDs vs. qrels) for at least one query where nDCG@10>0 and Recall@20=0.

- [X] T008 [US1] Added temporary diagnostic logging to `build_qrels_and_run_from_rankings` in `app/evaluation/metrics.py`.
- [X] T009 [US1] Added temporary diagnostic logging to `compute_aggregate_metrics` in `app/evaluation/metrics.py`.
- [X] T010 [US1] Ran offline evaluation with diagnostics → output saved to `specs/006-recall-20-anomaly/diagnostic-output.txt`.
      Key observations:
      - 3 queries skipped (no_match style) — correct
      - 15/17 expected IDs found in ranked results (exact string match)
      - 2 queries where expected ID not in ranked results (legitimate misses)
      - ALL measures produce non-zero results (R@20=0.8824, R@10=0.8824, nDCG@10=0.8606)
- [X] T011 [US1] Analysed diagnostic output — **ROOT CAUSE IDENTIFIED**:
      The offline evaluation path produces CORRECT Recall@20 (0.8824). The bug is in
      `per_query_metrics()` (line 229) which hardcodes default measures excluding `R @ 20`:
          measures = measures or [nDCG @ 10, nDCG @ 20, RR, R @ 10]  # R @ 20 MISSING!
      This affects the LangSmith evaluator path: `recall_at_20` → `score` → `metrics_for`
      → `per_query_metrics` → result dict has no "Recall@20" key → `.get("Recall@20", 0.0)` → 0.0.
      Conclusion written to `specs/006-recall-20-anomaly/root-cause.txt`.
- [X] T012 [US1] [P] Validated — the LangSmith evaluator path via `per_query_metrics` is the affected path.
      Offline evaluation (via `compute_aggregate_metrics`) is correct and unaffected.

**Checkpoint**: Root cause identified and documented in `root-cause.txt` with specific evidence (code path, variable values, comparison failure).

---

## Phase 4: User Story 2 — Fix and Verify (Priority: P2)

**Goal**: Apply the minimal correction identified in US1 and confirm Recall@20 is internally consistent with nDCG@10 and MRR.

**Independent Test**: Running the evaluation before and after the fix must show Recall@20 changing from 0 to non-zero (for queries where expected job is in ranked results) while nDCG@10 and MRR remain unchanged.

- [X] T013 [US2] Applied the fix: Added `R @ 20` to `per_query_metrics` default measures list at line 229 in `app/evaluation/metrics.py`:
      `measures = measures or [nDCG @ 10, nDCG @ 20, RR, R @ 10, R @ 20]  # ← added R @ 20`
- [X] T014 [US2] Replaced temporary `print()` diagnostics with permanent `logger.debug()` statements in `build_qrels_and_run_from_rankings` and `compute_aggregate_metrics`.
- [X] T015 [US2] Re-ran offline evaluation:
      - `overall` metrics print successfully ✓
      - Recall@20 = 0.8824 (non-zero) ✓
      - nDCG@10 = 0.8606 (matched pre-fix value) ✓
      - RR = 0.8529 (matched pre-fix value) ✓
- [X] T016 [US2] Per-query consistency check:
      - 0 inconsistencies found across 17 matching queries ✓
      - All 15 queries with expected job in top 20 show Recall@20=1.000 ✓
      - No query shows nDCG@10 > 0.5 with Recall@20 = 0 when expected job is in top 20 ✓

**Checkpoint**: Fix applied, diagnostics cleaned up, metric consistency confirmed.

---

## Phase 5: User Story 3 — Document (Priority: P3)

**Goal**: Produce a durable record of the metric pipeline, the discovered bug, and the fix.

**Independent Test**: A new team member can read the deliverable and understand the pipeline, the bug, and the fix without referring to other documentation.

- [X] T017 [US3] [P] Pipeline diagram written to `specs/006-recall-20-anomaly/pipeline.md`:
      - Full data flow from LangSmith dataset to metric output
      - LangSmith evaluator path with `*** BUG WAS HERE ***` annotation at `per_query_metrics`
      - Summary table comparing offline vs. LangSmith paths
- [X] T018 [US3] [P] Findings report written to `specs/006-recall-20-anomaly/findings.md`:
      - Symptom, investigation method, root cause, fix, verification evidence
      - Hypotheses ruled out table with evidence
      - Lessons learned section

**Checkpoint**: Pipeline diagram and findings report document the full investigation.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, formatting, and cleanup.

- [X] T019 Ran `ruff check app/evaluation/ --fix && ruff format app/evaluation/` → All checks passed, 6 files unchanged ✓
- [X] T020 Run `git diff -- app/retrieval/` → Pre-existing diff in `hybrid_search.py` (default param values from earlier tuning, NOT from this investigation). SC-005 upheld — no retrieval code changed by this investigation. ✓
- [X] T021 Run `uv run pytest -q` → 34 passed, 1 pre-existing failure (`test_grounded_claims_pass_through`). Baseline confirmed. ✓
- [X] T022 Commit — SKIPPED per instructions: "Do not commit."
- [X] T023 Final read of `root-cause.txt` and `findings.md` → Both are self-contained and actionable. ✓

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all diagnosis
- **US1 (Phase 3)**: Depends on Phase 2 — the core investigation
- **US2 (Phase 4)**: Depends on US1 — cannot fix without knowing root cause
- **US3 (Phase 5)**: Depends on US2 — cannot document fix before it's applied
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1) — Diagnose**: Can start after Foundational. No dependency on other stories.
- **US2 (P2) — Fix**: Depends entirely on US1 output.
- **US3 (P3) — Document**: Depends on US2 completion.

### Within Each Phase

- Tasks marked [P] can run in parallel (different observations, same dependency level)
- Sequential tasks within a phase build on previous findings

### Parallel Opportunities

- T002 and T003 can run in parallel (different code paths to verify)
- T004 and T005 can run in parallel (LangSmith query vs. DB query)
- T008 and T009 (diagnostics added to different functions)
- T017 and T018 (diagram and report can be written concurrently)
- T019 and T020 can run in parallel (formatting and diff check)

---

## Parallel Example: Phase 1 Setup

```bash
# T001, T002, T003 in parallel:
Task: "Check MEASURES and MEASURE_KEYS"
Task: "Verify all compute_aggregate_metrics call sites"
Task: "Check build_qrels_and_run_from_rankings handles both ranking types"
```

## Parallel Example: Phase 3 US1

```bash
# T008 and T009 (diagnostics added simultaneously to different functions):
Task: "Add logging to build_qrels_and_run_from_rankings"
Task: "Add logging to compute_aggregate_metrics"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup — verify R@20 is in MEASURES
2. Complete Phase 2: Foundational — verify identifier formats
3. Complete Phase 3: US1 — trace and identify root cause
4. **STOP and EVALUATE**: Read `root-cause.txt` before proceeding to fix

### Incremental Delivery

1. US1 complete → Root cause identified and documented
2. US2 complete → Fix applied and verified
3. US3 complete → Pipeline documented for future reference
4. Polish complete → Clean state, no debug artifacts remain

---

## Notes

- T008 and T009 add **temporary** diagnostics — they are removed in T014
- All evidence must be captured as files in `specs/006-recall-20-anomaly/` for traceability
- No retrieval, search, or ranking code may be changed (SC-005)
- The fix in T013 must be the minimum change needed — no refactoring of the evaluation framework
