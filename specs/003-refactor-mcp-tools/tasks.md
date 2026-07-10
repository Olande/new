# Tasks: MCP Tools Layer Refactoring

## Format: `[ID] [P?] [Story] Description`

- `[ID]` is a sequential identifier (`T001`, `T002`, ...).
- `[P]` indicates a task that can be executed in parallel.
- `[Story]` is the user story label (e.g., `[US1]`).

## Path Conventions
- Repositories: `app/mcp/repositories/`
- Services: `app/mcp/services/`
- Tool Entrypoint: `app/mcp/mcp_server.py`
- Test Suite: `tests/`

---

## Phase 1: Setup (Shared Infrastructure)
- [X] T001 Create repository and service directories: `app/mcp/repositories/` and `app/mcp/services/`.

## Phase 2: Foundational (Blocking Prerequisites)
- [X] T002 Implement domain exception models (`DomainException`, `NotFoundError`, `UnauthorizedError`, `ValidationError`) in `app/mcp/exceptions.py`.
- [X] T003 Implement `@translate_mcp_exceptions` decorator to convert domain exceptions to standard `ErrorResponse` DTO outputs in `app/mcp/exceptions.py`.
- [X] T004 Implement session helper context managers and JWT authorization dependency providers in `app/mcp/di.py`.

## Phase 3: User Story 1 - Reduced Boilerplate & High Maintainability (Priority: P1) 🎯 MVP

### Implementation for User Story 1
- [X] T005 [P] [US1] Create `JobRepository` with `search` and `get_by_id` query methods in `app/mcp/repositories/job_repo.py`.
- [X] T006 [P] [US1] Create `JobService` with search and get logic returning Pydantic DTO output in `app/mcp/services/job_service.py`.
- [X] T007 [P] [US1] Create `ApplicationRepository` with create and ownership retrieval in `app/mcp/repositories/app_repo.py`.
- [X] T008 [P] [US1] Create `ApplicationService` scoping transactions and draft creation workflows in `app/mcp/services/app_service.py`.

## Phase 4: User Story 2 - Automated Tenant-Isolated Authorization (Priority: P1)

### Implementation for User Story 2
- [X] T009 [P] [US2] Create `UserRepository` retrieving user records in `app/mcp/repositories/user_repo.py`.
- [X] T010 [P] [US2] Create `CareerMemoryRepository` querying user memories in `app/mcp/repositories/memory_repo.py`.
- [X] T011 [US2] Create `ProfileService` aggregating profile statistics and memory mappings with tenant checks in `app/mcp/services/profile_service.py`.

## Phase 5: User Story 3 - Centralized Exception Translation (Priority: P2)

### Implementation for User Story 3
- [X] T012 [P] [US3] Create `AgentTaskRepository` in `app/mcp/repositories/task_repo.py` and `SubmissionService` orchestrating approvals in `app/mcp/services/submission_service.py`.
- [X] T013 [US3] Refactor `app/mcp/mcp_server.py` to replace database session loops with service class delegates and `@translate_mcp_exceptions`.
- [X] T014 [US3] Write unit/integration tests checking that exceptions translate correctly to `ErrorResponse` DTO structures in `tests/test_mcp.py`.

## Phase 6: Polish & Cross-Cutting Concerns
- [X] T015 Run `pytest` to confirm all graph and MCP server tests pass.
- [X] T016 Run `ruff check` and `ruff format` on the newly refactored files.

---

## Dependencies & Execution Order

### Phase Dependencies
- Phase 1 (Setup) and Phase 2 (Foundational) must complete before any User Story tasks.
- Phase 3 (US1) is the MVP and must be completed before Phase 4 (US2) and Phase 5 (US3).

### Parallel Opportunities
- T005, T007, T009, and T010 can be built and unit-tested in parallel as they cover separate repository classes.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
Ensure that the `JobRepository` and `JobService` are fully functional and verified before building profile or submission services.

### Incremental Delivery
Deliver each phase in a clean, compile-safe PR with accompanying tests to ensure no regressions in current features.
