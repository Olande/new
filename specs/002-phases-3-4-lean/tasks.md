# Tasks: Phases 3-4 Lean Refactoring

## Format: `[ID] [P?] [Story] Description`

- `[ID]` is a sequential identifier (`T001`, `T002`, ...).
- `[P]` indicates a task that can be executed in parallel.
- `[Story]` is the user story label (e.g., `[US1]`).

## Path Conventions
- Graph Engine: `app/graph/`
- MCP Server: `app/mcp/`
- Core Models: `app/core/db/models/`
- Database Settings & Core: `app/core/db/` and `app/core/config/`

---

## Phase 1: Setup (Shared Infrastructure)
- [X] T001 Verify `psycopg` and `psycopg_pool` are present in `pyproject.toml` and lock files.
- [X] T002 Verify `langgraph-checkpoint-postgres` and `langgraph-store-postgres` dependency declarations.

## Phase 2: Foundational (Blocking Prerequisites)
- [X] T003 Implement `mcp_context.py` using stdlib `ContextVar` to manage task-local request contexts (`user_id`, `tenant_id`) in `app/mcp/mcp_context.py`.
- [X] T004 Define inputs and outputs using Pydantic models in `app/mcp/mcp_schemas.py`.

## Phase 3: User Story 1 - Relational Persistence & State Preservation (Priority: P1) 🎯 MVP

### Implementation for User Story 1
- [X] T005 [P] Implement `build_qa_graph_postgres` async context manager factory using `psycopg_pool.AsyncConnectionPool` inside `app/graph/agent.py`.
- [X] T006 [P] Add check in `build_qa_graph` to raise `ValueError` if the checkpointer instance is memory-based in `app/graph/agent.py`.
- [X] T007 [P] [US1] Implement `load_career_memories_from_store(store, user_id)` helper using `store.asearch` in `app/graph/nodes.py`.
- [X] T008 [P] [US1] Implement `migrate_career_memory_table_to_store(db, store, user_id)` helper copying active memories in `app/graph/nodes.py`.
- [X] T009 [US1] Update `analyze_query` node to call `load_career_memories_from_store` to augment prompt in `app/graph/nodes.py`.

## Phase 4: User Story 2 - Automated Application Submission with HIL (Priority: P1)

### Implementation for User Story 2
- [X] T010 [US2] Update transient `QAGraphState` in `app/graph/graph_state.py` with submission and critique fields.
- [X] T011 [US2] Implement graph nodes (`intent_router`, `prepare_submission`, `execute_submission`) in `app/graph/nodes.py`.
- [X] T012 [US2] Implement `request_human_approval` with `interrupt()` call in `app/graph/nodes.py`.
- [X] T013 [US2] Compile graph routes including submission and critique loops in `app/graph/agent.py`.
- [X] T014 [US2] Write unit/integration tests for human interrupt workflow in `tests/test_graph.py`.

## Phase 5: User Story 3 - Tenant-Isolated MCP Server & Tools (Priority: P2)

### Implementation for User Story 3
- [X] T015 [US3] Implement Starlette `BaseHTTPMiddleware` to extract bearer tokens from the `Authorization` header and populate request context in `app/mcp/mcp_context.py`.
- [X] T016 [US3] Refactor `mcp_server.py` to be a thin FastMCP router (<150 LOC) importing granular tool functions in `app/mcp/mcp_server.py`.
- [X] T017 [US3] Enforce `get_current_user_id()` checks on all tool db queries and verify cross-tenant access limits in `app/mcp/mcp_server.py`.
- [X] T018 [US3] Write integration tests verifying tenant isolation blocks cross-tenant access in `tests/test_mcp.py`.

## Phase 6: Polish & Cross-Cutting Concerns
- [X] T019 Run full test suite (`pytest`) to confirm no regressions in graph operations.
- [X] T020 Run `ruff format` and `ruff check` on the updated files to verify compliance.

---

## Dependencies & Execution Order

### Phase Dependencies
- Phase 1 (Setup) and Phase 2 (Foundational) must complete before any User Story tasks.
- Phase 3 (US1) is the MVP and must be completed before Phase 4 (US2) and Phase 5 (US3).

### Parallel Opportunities
- T005, T006, T007, and T008 can be built and unit-tested in parallel as they cover separate helper functions.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
Ensure that the Postgres checkpointer/store and CareerMemory migration logic are fully functional and verified before building advanced routing and human-in-the-loop steps.

### Incremental Delivery
Deliver each phase in a clean, compile-safe PR with accompanying tests to ensure no regressions in current features.
