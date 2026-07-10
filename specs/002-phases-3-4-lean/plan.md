# Implementation Plan: Phases 3-4 Lean Refactoring

**Branch**: `phase4-infra-decoupling` | **Date**: 2026-07-10 | **Spec**: [spec.md](file:///home/olande/PycharmProjects/fun_project/specs/002-phases-3-4-lean/spec.md)

## Summary
Re-implement Phases 3 and 4 of the CareerPilot platform to enforce a lean, library-first architecture. This refactor implements Postgres checkpointers, CareerMemory store synchronization, standard LangGraph routing primitives, thin/modular MCP tools, and request-context tenant isolation.

## Technical Context
- **Language/Version**: Python 3.13+
- **Primary Dependencies**: `langgraph`, `langgraph-checkpoint-postgres`, `langgraph-store-postgres`, `psycopg_pool`, `pydantic`, `pyjwt`, `starlette`, `fastmcp`
- **Testing**: `pytest`
- **Project Type**: Agentic platform with relational database backing

## Constitution Check
*GATE: Passes all checks under the core principles of CareerPilot Constitution.*
1. **Decoupled Architecture & Module Isolation**: The codebase is split into granular files under `app/graph/nodes/` and `app/mcp/tools/`, preventing `mcp_server.py` from becoming a monolithic "god file".
2. **Rigorous Testing Discipline & Migration Safety**: Postgres Store setup and HIL interrupts are designed to be fully testable with mock connections.

## Project Structure

### Source Code
- `app/graph/agent.py`: Exposes `build_qa_graph` and `build_qa_graph_postgres` context manager.
- `app/graph/graph_state.py`: Defines the transient thread state schema using `QAGraphState`.
- `app/graph/nodes.py`: Declares the Store-to-CareerMemory bridge functions and node definitions.
- `app/mcp/mcp_server.py`: FastMCP entrypoint server (<150 LOC).
- `app/mcp/mcp_schemas.py`: Pydantic input/output schemas for all MCP tools.
- `app/mcp/mcp_context.py`: Thread/task local request context and tenant isolation middleware.

## Proposed Changes

### 1. Postgres Checkpointer (`app/graph/agent.py`)
- Remove all memory fallback mechanisms.
- Require `AsyncPostgresSaver` and `AsyncPostgresStore` initialized with `AsyncConnectionPool`.
- Throw a `ValueError` inside `build_qa_graph` if a memory saver is passed.

### 2. CareerMemory Store Bridge (`app/graph/nodes.py`)
- Map the legacy relational database `career_memory` table rows to the Postgres Store using `namespace=(str(user_id), entity_type.value)`.
- Implement `load_career_memories_from_store` to fetch memories via `store.asearch` and augment prompts.
- Implement `migrate_career_memory_table_to_store` to copy active memories (where `valid_to IS NULL`) into the Store.

### 3. Graph Topology (`app/graph/agent.py` & `app/graph/nodes.py`)
- Structure query routing using standard `Send` and `Command` primitives.
- Implement a structured validation loop: `generate_draft` -> `heuristic_check` -> `llm_critic` -> `END`.
- Implement HIL submission logic: `prepare_submission` -> `request_human_approval` (triggers `interrupt`) -> `execute_submission` (enforces `state.user_id == application.user_id`).

### 4. Tenant Isolation & Middleware (`app/mcp/mcp_context.py`)
- Implement task-local `ContextVar` to isolate user and tenant identities.
- Create Starlette `BaseHTTPMiddleware` to extract bearer tokens from the `Authorization` header and populate the context variable.
- Enforce check constraints in database queries to ensure all operations filter by the current isolated user ID.

### 5. Granular MCP Tools (`app/mcp/mcp_server.py` & `app/mcp/tools/`)
- Deconstruct the monolithic `mcp_server.py` into small, single-purpose functions under `<50` lines.
- Expose public endpoints for job search, job details, profile management, and draft submission.

## Complexity Tracking
- **Postgres checkpointer integration**: Low complexity, standard library imports.
- **Human-in-the-loop interrupts**: Medium complexity, requires test validation.
- **Tenant isolation middleware**: Medium complexity, requires verification of header parsing logic.
