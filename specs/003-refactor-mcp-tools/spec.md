# Feature Specification: MCP Tools Layer Refactoring

**Feature Branch**: `phase4-infra-decoupling`
**Created**: 2026-07-10
**Status**: Draft

## User Scenarios & Testing

### User Story 1 - Reduced Boilerplate & High Maintainability (Priority: P1) 🎯 MVP
As a developer maintaining the MCP platform, I want a clean, decoupled structure for tools so that I can add new features quickly without copy-pasting session and authorization boilerplate.

**Independent Test**: Verify that the lines of code in the transport/tool entrypoints are reduced by at least 50% after moving database querying, transaction boundaries, and business validation into a modular service and repository layer.

**Acceptance Scenarios**:
1. **Given** a new MCP tool is added, **When** it receives a query, **Then** it delegates execution to the service layer and returns standard DTOs without manual session context management.

### User Story 2 - Automated Tenant-Isolated Authorization (Priority: P1)
As a developer, I want current user context and tenant identities to be resolved automatically and injected into service tasks, preventing data access leakage.

**Independent Test**: Verify that calling tools with missing or malformed authentication tokens automatically rejects execution at the border with a standard unauthorized message, and valid requests isolate database operations by user ID.

**Acceptance Scenarios**:
1. **Given** a tool call, **When** no token or an invalid token is provided, **Then** the request is blocked and returned as unauthorized.
2. **Given** a valid token, **When** database queries run, **Then** results are automatically isolated by the resolved user context.

### User Story 3 - Centralized Exception Translation (Priority: P2)
As a developer, I want standard domain exceptions to be handled centrally so that my code does not require duplicative `try/except` blocks in every tool method.

**Independent Test**: Verify that domain exceptions (e.g., entity not found, validation error, permission denied) thrown in the repository or service layers are caught by a central translator and converted to standardized error responses.

**Acceptance Scenarios**:
1. **Given** a query for a non-existent job ID, **When** the service raises a `NotFoundError`, **Then** the MCP response formats this into an error structure with a corresponding error code.

---

## Edge Cases
- **Database Connection Failures**: Centralized exception handler should capture raw SQLAlchemy connection errors and return a user-friendly database connection failure message rather than crashing the server.
- **Malformed JWT Claims**: Handles malformed/empty sub payloads in token extraction and returns an unauthorized error response.

---

## Requirements

### Functional Requirements
* **FR-301 (Layered Boundaries)**: The tools layer MUST be decoupled into a Tool/Transport Layer, a Service Layer (business logic, validation), and a Repository Layer (database queries, persistence).
* **FR-302 (Dependency Injection)**: The system MUST resolve and inject database sessions and current authenticated user objects directly to avoid manual context lookups.
* **FR-303 (Centralized Auth)**: Token parsing and tenant isolation checking MUST be unified, using context propagation to secure database filters.
* **FR-304 (Unified Exception Handling)**: Custom domain exceptions (e.g., authorization, validation, not found) MUST be captured centrally and translated to `ErrorResponse` formats without exposing stack traces.
* **FR-305 (Standardized DTO Serialization)**: Tool methods MUST use Pydantic models for request input and response serialization to maintain external API compatibility.

### Key Entities
* **AuthenticatedUser**: Object carrying parsed identities and permissions.
* **Job, Application, AgentTask, CareerMemory**: Domain entities queried through repository interfaces.

---

## Success Criteria

### Measurable Outcomes
* **SC-301**: The code volume in the transport-level tool wrappers (e.g., `mcp_server.py`) is reduced by at least 50%.
* **SC-302**: Zero manual session managers (`async_session()`) inside the tool wrapper endpoints.
* **SC-303**: Standard domain exceptions result in formatted error outputs without raw system trace leaks.
