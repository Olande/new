# Implementation Plan: Loop & Evaluation Optimization

**Branch**: `phase4-infra-decoupling` | **Date**: 2026-07-10 | **Spec**: [spec.md](file:///home/olande/PycharmProjects/fun_project/specs/001-loop-eval-optimization/spec.md)

## Summary
Refactor the retrieval evaluation framework to reduce lines of code and simplify its design by consolidating several small/redundant files. Delete the empty/shim test files under `app/tests/evaluation/`. Create a root `tests/` directory with smoke tests for evaluation to satisfy and fix the CI/CD pipeline which runs `uv run pytest tests/`. Correct the broken relative paths in `LOOP.md` and clean up untracked tool directories using `.gitignore`.

## Technical Context
- **Language/Version**: Python 3.13+
- **Primary Dependencies**: `ir-measures`, `langsmith`, `sqlalchemy`, `loguru`, `pydantic`
- **Testing**: `pytest`, `pytest-asyncio`
- **Project Type**: LLM application evaluation harness

## Constitution Check
*GATE: Passes all checks under the core principles of CareerPilot Constitution.*
1. **Decoupled Architecture & Module Isolation**: The evaluation package `app.evaluation` is a separate domain. Consolidating its internal files respects isolation and removes unnecessary forwarding paths.
2. **Deterministic Vector Search & Embeddings**: No changes are made to embeddings computation.
3. **Rigorous Testing Discipline & Migration Safety**: Adding a new test suite under `tests/` ensures that future changes are covered. No database schema changes are introduced.

## Proposed Changes

### 1. Evaluation Refactor (app/evaluation/)
Consolidate the evaluation files to eliminate boilerplate and reduce files with only a few lines:
- **`app/evaluation/search.py`**:
  - Incorporate contents of `constants.py` (e.g. `SearchParams`, `DEFAULT_SEARCH_PARAMS`, `RETRIEVAL_DATASET`).
  - Incorporate contents of `targets.py` (e.g. `retrieval_target`).
- **`app/evaluation/metrics.py`**:
  - Incorporate contents of `evaluators.py` (e.g. `ndcg_at_10`, `ndcg_at_20`, `mrr`, `recall_at_10`, `recall_at_20`, `RETRIEVAL_EVALUATORS`, and the metrics cache).
- **`app/evaluation/run_eval.py`**:
  - Incorporate contents of `regression.py` (e.g. `check_retrieval_regression`, `get_feedback_avg`, `relative_drop`).
- **`app/evaluation/__init__.py`**:
  - Update imports and `__all__` to match new consolidated modules.
- **Delete Files**:
  - `app/evaluation/constants.py` [DELETE]
  - `app/evaluation/targets.py` [DELETE]
  - `app/evaluation/evaluators.py` [DELETE]
  - `app/evaluation/regression.py` [DELETE]

---

### 2. Remove Deprecated Evaluation Shims (app/tests/evaluation/)
- **Delete Files**:
  - `app/tests/evaluation/__init__.py` [DELETE]
  - `app/tests/evaluation/evaluators.py` [DELETE]
  - `app/tests/evaluation/run_eval.py` [DELETE]

---

### 3. Create Unit/Smoke Tests (tests/)
Create a dedicated `tests/` directory at the root containing unit tests for evaluation helpers:
- **`tests/test_evaluation.py` [NEW]**:
  - Test `query_style_of` with sample LangSmith examples.
  - Test `expected_job_id_of` with valid, empty, and None examples.
  - Test `is_matching_example`.
  - Test `per_query_metrics` using mock `ir-measures` output.
  - Test `check_retrieval_regression` and other mathematical functions like `relative_drop`.

---

### 4. Loop & Repository Configuration
- **`LOOP.md` [MODIFY]**:
  - Replace broken relative links to `../../patterns/daily-triage.md` and `../../docs/loop-design-checklist.md` with:
    - Pattern: `[daily-triage](skills/loop-triage/SKILL.md)`
    - Checklist: `[loop-design-checklist](loop-constraints.md)`
- **`.gitignore` [MODIFY]**:
  - Add `.grok/`, `.agents/`, `.specify/` to prevent untracked tool directories from polluting `git status`.
- **`.github/workflows/ci.yml` [MODIFY]**:
  - Update `paths` triggers to match `app/evaluation/**` and `app/graph/**` instead of `app/agents/**`.

## Verification Plan

### Automated Tests
Run the entire test suite locally to verify success:
```bash
pytest
```
And verify the specific new smoke tests:
```bash
pytest tests/
```

### Manual Verification
1. Run local offline evaluation grid search or dry run:
   ```bash
   python -m app.evaluation.run_local --limit 5
   ```
2. Check git status to ensure untracked directories like `.grok/`, `.agents/`, `.specify/` are ignored:
   ```bash
   git status
   ```
