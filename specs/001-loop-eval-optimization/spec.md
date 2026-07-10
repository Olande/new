# Feature Specification: Loop & Evaluation Optimization

**Feature Branch**: `phase4-infra-decoupling`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User request: "read through the loop.md find the issues generate a plan to fix them, then using web search capabilities, the entire evaluation despite working is too verbose, find libraries and or better python to reduce the loc, some files have like 3 lines of code related to evaluation, we need to group them!"

## User Scenarios & Testing (Priority: P1)

### User Story 1 - Consolidate Evaluation Codebase (Priority: P1)
As a developer, I want the evaluation framework to be streamlined and consolidated into fewer, cohesive modules, so that the codebase is easy to maintain and has minimal boilerplate.

**Why this priority**: Highly critical to reduce the verbosity and LOC of the codebase.
**Independent Test**: Verify that running evaluations locally (`python -m app.evaluation.run_local`) and on LangSmith (`python -m app.evaluation.run_eval`) produces identical results to the original codebase.

**Acceptance Scenarios**:
1. **Given** the consolidated evaluation codebase, **When** running `python -m app.evaluation.run_local`, **Then** it must correctly compute overall and per-style metrics.
2. **Given** the consolidated evaluation codebase, **When** running `python -m app.evaluation.run_eval`, **Then** it must perform LangSmith evaluations and regression checking.

### User Story 2 - Fix Loop Configuration & Broken Links (Priority: P2)
As an operator, I want the loop configuration files and links to be correct and verified, so that the opencode loops execute without errors or broken path references.

**Why this priority**: Essential for loop integrity and repository hygiene.
**Independent Test**: Inspect `LOOP.md` and check that all relative links resolve to valid, existing project files.

**Acceptance Scenarios**:
1. **Given** the updated `LOOP.md`, **When** clicking links to pattern and checklist docs, **Then** they must lead to actual files.

### User Story 3 - Repair CI/CD and Add Smoke Tests (Priority: P2)
As a maintainer, I want the CI pipeline to pass and run tests correctly, so that regression checks are active on PRs.

**Why this priority**: Fixes the broken `uv run pytest tests/` CI run command.
**Independent Test**: Run `pytest tests/` locally and verify that it finds and executes the new smoke tests successfully.

**Acceptance Scenarios**:
1. **Given** a new root `tests/` directory with `tests/test_evaluation.py` smoke tests, **When** running `pytest tests/`, **Then** the tests must pass successfully.

---

## Edge Cases
- **LangSmith Credentials missing**: `run_eval.py` must handle missing `LANGSMITH_API_KEY` gracefully and exit early.
- **Empty Retrieval Result**: Metrics computation must handle queries that return 0 hits or are omitted from the search results without throwing exceptions.

## Requirements

### Functional Requirements
- **FR-001**: The evaluation package `app.evaluation` MUST contain at most 4 primary modules: `search.py`, `metrics.py`, `run_eval.py`, and `run_local.py`.
- **FR-002**: `constants.py` and `targets.py` MUST be merged into `search.py`.
- **FR-003**: `evaluators.py` MUST be merged into `metrics.py`.
- **FR-004**: `regression.py` MUST be merged into `run_eval.py`.
- **FR-005**: All empty/shim files in `app/tests/evaluation/` MUST be deleted.
- **FR-006**: `LOOP.md` MUST have valid links pointing to the project's config templates or markdown docs.
- **FR-007**: A root `tests/` directory MUST be created containing smoke tests in `tests/test_evaluation.py` covering pure evaluation helper functions.
- **FR-008**: Stale/deleted path filters in `.github/workflows/ci.yml` MUST be updated.
- **FR-009**: `.gitignore` MUST be updated to ignore tool directories like `.grok/`, `.agents/`, and `.specify/`.

## Success Criteria

### Measurable Outcomes
- **SC-001**: Total lines of code in `app/evaluation` is reduced by at least 20%.
- **SC-002**: `pytest tests/` runs successfully with zero errors.
- **SC-003**: Git working tree is clean of untracked tool directories.
