# Feature Specification: MCP Server

**Status**: Migrated (reverse-engineered from code)
**Branch**: `phase4-infra-decoupling`
**Migrated**: 2026-07-10

## User Scenarios

### User Story 1 — Job Search & Discovery (Priority: P1)

Users search for jobs using natural language queries and retrieve full job details with descriptions.

**Acceptance Scenarios**:

1. **Given** indexed jobs in the database, **When** a user calls `search_jobs_tool` with a query, **Then** hybrid search results (BM25 + cosine) are returned with relevance scores
2. **Given** a search result, **When** the user calls `get_job_tool` with a job ID, **Then** full job details including description text are returned

### User Story 2 — Application Management (Priority: P1)

Users create draft applications and submit them through a human-in-the-loop approval flow.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they call `create_application_draft_tool`, **Then** a draft application is saved with resume, cover letter, and notes
2. **Given** a draft application exists, **When** the user calls `submit_application_tool`, **Then** a pending `AgentTask` is created for human approval
3. **Given** a pending submission task, **When** a reviewer calls `confirm_submission_tool(approved=true)`, **Then** the application is submitted and the task marked completed

### User Story 3 — Profile & Memory Access (Priority: P2)

Authenticated users retrieve their profile and career memory history.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they call `get_my_profile_tool`, **Then** their email and career memories are returned

## Requirements

### Functional Requirements

- **FR-001**: System MUST expose tools via the `FastMCP` protocol (SSE + stdio transports)
- **FR-002**: System MUST authenticate requests via JWT token extracted from Authorization header
- **FR-003**: System MUST enforce tenant isolation via middleware (user_id + tenant_id context)
- **FR-004**: System MUST search jobs using hybrid search (BM25 + vector cosine similarity)
- **FR-005**: System MUST support configurable cosine similarity threshold (default 0.5)
- **FR-006**: System MUST return full job descriptions on `get_job_tool`
- **FR-007**: System MUST create draft applications with resume, cover letter, and notes
- **FR-008**: System MUST require human approval via `confirm_submission_tool` for submissions
- **FR-009**: System MUST create `AgentTask` records for pending submissions
- **FR-010**: System MUST return user profile including career memories
- **FR-011**: System MUST translate domain exceptions (`NotFoundError`, `ValidationError`, `UnauthorizedError`) to structured `ErrorResponse` dicts

### Key Entities

- **FastMCP Server**: `mcp` instance with 5 tool registrations
- **MCP Schemas**: 12 Pydantic models for tool input/output validation
- **Repositories**: 5 data access objects (Job, Application, User, Memory, Task)
- **Services**: 4 business logic services (Job, Application, Profile, Submission)
- **Middleware**: Tenant context extraction from JWT with per-request lifecycle

## Success Criteria

- **SC-001**: All 5 MCP tools respond correctly with validated Pydantic output
- **SC-002**: Search results return hybrid scores combining BM25 and vector similarity
- **SC-003**: Application submission requires two-phase confirm/cancel (HIL)
- **SC-004**: Unauthenticated requests are rejected with `UnauthorizedError`
- **SC-005**: Domain exceptions are consistently translated to `ErrorResponse` format
- **SC-006**: Test coverage exists for all 5 MCP tool endpoints (`tests/test_mcp.py`)

## Assumptions

- `FastMCP` from `mcp[fastmcp]` package handles SSE and stdio transports
- JWT tokens are opaque strings validated externally (no key validation in MCP)
- Application submissions always require human approval (no auto-submit mode)
