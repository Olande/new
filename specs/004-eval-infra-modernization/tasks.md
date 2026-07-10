# Tasks: Evaluation Infrastructure Modernization

**Input**: Design documents from `/specs/004-eval-infra-modernization/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Add Typer and Optuna to project dependencies in pyproject.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Refactor metrics formatting and aggregation helpers in app/evaluation/metrics.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Automatic Regression Detection (Priority: P1) 🎯 MVP

**Goal**: Run evaluations on LangSmith, fetch feedbacks, compare against prior run averages, and fail if degradation exceeds thresholds.

**Independent Test**: Execute `run_eval.py` and verify it detects and logs regression or succeeds when baseline is met.

### Tests for User Story 1

- [X] T003 [P] [US1] Create unit tests for regression comparison in tests/test_evaluation.py

### Implementation for User Story 1

- [X] T004 [US1] Refactor check_retrieval_regression to query LangSmith API and check thresholds in app/evaluation/run_eval.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Automated Hyperparameter Optimization (Priority: P2)

**Goal**: Run Optuna study to discover optimal parameters.

**Independent Test**: Execute the optimize command and verify the best weights are logged.

### Tests for User Story 2

- [X] T005 [P] [US2] Create unit tests for Optuna parameter optimization execution in tests/test_evaluation.py

### Implementation for User Story 2

- [X] T006 [US2] Implement Optuna study optimization run target in app/evaluation/run_local.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Local Benchmarking CLI with Input Validation (Priority: P3)

**Goal**: Create the Typer CLI replacing argparse.

**Independent Test**: Execute CLI command with invalid options and verify validation stops execution.

### Tests for User Story 3

- [X] T007 [P] [US3] Create command line interface tests verifying validation errors in tests/test_evaluation.py

### Implementation for User Story 3

- [X] T008 [US3] Implement Typer CLI commands for evaluate and optimize in app/evaluation/run_local.py

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T009 Run quickstart.md validation guide scenarios
- [X] T010 [P] Execute the entire test suite in tests/test_evaluation.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2)
- **User Story 3 (P3)**: Can start after Foundational (Phase 2)

### Within Each User Story

- Tests must be written and verify execution
- Core implementation before integration
- Story complete before moving to next priority

---

## Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel

---

## Parallel Example: User Stories 1 & 2

```bash
# Launch tests for User Story 1 and 2 in parallel
Task T003: "Create unit tests for regression comparison in tests/test_evaluation.py"
Task T005: "Create unit tests for Optuna parameter optimization execution in tests/test_evaluation.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently
3. Add User Story 2 → Test independently
4. Add User Story 3 → Test independently
