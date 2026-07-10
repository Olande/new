# Feature Specification: Phases 3-4 Lean Refactoring

**Feature Branch**: `phase4-infra-decoupling`
**Created**: 2026-07-10
**Status**: Draft

## User Scenarios & Testing

### User Story 1 - Relational Persistence & State Preservation (Priority: P1)
As a user, I want my interactive job search and application session to be preserved across server restarts, so that my context is not lost.

**Independent Test**: Verify that the StateGraph checkpointer and store successfully save thread state and career memories to PostgreSQL database, and that in-memory mock savers are blocked in production.

**Acceptance Scenarios**:
1. **Given** a Postgres database, **When** the LangGraph agent is compiled, **Then** it must use `AsyncPostgresSaver` and `AsyncPostgresStore` with no in-memory fallbacks.
2. **Given** a compiled graph, **When** invoking it with a thread ID, **Then** thread state is stored and retrieved from the database.

### User Story 2 - Automated Application Submission with HIL (Priority: P1)
As a user, I want to submit a job application and have the system ask for my explicit approval before final submission.

**Independent Test**: Verify that the LangGraph submission path halts at the human approval step and triggers an interrupt.

**Acceptance Scenarios**:
1. **Given** a submission intent, **When** the workflow reaches `request_human_approval`, **Then** the execution is interrupted to wait for approval.
2. **Given** a user approves, **When** the execution resumes, **Then** the application status in the database is updated to "submitted".

---

## Requirements

### Functional Requirements
* **FR-101 (Postgres Checkpointer)**: The graph MUST use Postgres checkpointer (`AsyncPostgresSaver`) and store (`AsyncPostgresStore`) via `psycopg_pool.AsyncConnectionPool` for database connection management.
* **FR-102 (Checkpointer Enforcement)**: The graph builder `build_qa_graph` MUST raise a `ValueError` if the provided checkpointer is an in-memory saver.
* **FR-103 (CareerMemory Store)**: User career memories MUST be mapped to the Postgres Store using `namespace=(str(user_id), entity_type.value)`.
* **FR-104 (Migration)**: A helper function `migrate_career_memory_table_to_store` MUST copy valid career memory table records to the Postgres Store.
* **FR-105 (Graph Topology)**: The graph MUST utilize LangGraph primitives (`StateGraph`, `Send`, `Command`, `interrupt`) for routing, verification loops, and human-in-the-loop approvals.
* **FR-106 (Granular MCP Tools)**: The MCP server MUST expose granular tools (<50 lines each) for searching jobs, getting details, creating drafts, submitting, and confirming submissions.
* **FR-107 (Tenant Isolation)**: The application MUST isolate tenant data using context variables (`mcp_context.py`), PyJWT for payload parsing, and Starlette middleware for authorization extraction.

### Key Entities
* **CareerMemory**: Mapped relational database model containing user career history.
* **AgentTask**: Table tracking long-running tasks, execution states, and pending submissions.
* **Application**: Table tracking drafts and submitted applications.

---

## Success Criteria

### Measurable Outcomes
* **SC-101**: Zero references to memory fallback checkpointers in production initialization.
* **SC-102**: Full tenant isolation verified by authorization header checks in the Starlette middleware.
* **SC-103**: Less than 150 lines of code in the main `mcp_server.py` entrypoint.
