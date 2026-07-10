# Implementation Plan: MCP Tools Layer Refactoring

**Branch**: `phase4-infra-decoupling` | **Date**: 2026-07-10 | **Spec**: [spec.md](file:///home/olande/PycharmProjects/fun_project/specs/003-refactor-mcp-tools/spec.md)

## Summary
Refactor the MCP tools layer to adopt a clean, decoupled layered architecture. This separates transport-layer routing from business logic (services) and data retrieval (repositories), introducing constructor-based dependency injection, centralized exception translation, and unified tenant-isolated security.

## Technical Context
- **Language/Version**: Python 3.13+
- **Primary Dependencies**: `fastmcp`, `sqlalchemy`, `pydantic`, `starlette`
- **Testing**: `pytest`, `pytest-asyncio`
- **Project Type**: Layered Python API

## Constitution Check
*GATE: Passes all checks under the core principles of CareerPilot Constitution.*
1. **Decoupled Architecture & Module Isolation**: Explicit boundaries separate the transport wrapper (`mcp_server.py`), repositories (`app/mcp/repositories/`), and services (`app/mcp/services/`).
2. **Strict Input Normalization**: Business parameters are validated at the service boundary.

## Project Structure

### Source Code
- `app/mcp/mcp_server.py`: FastMCP route definitions (acting as transport adapters only).
- `app/mcp/exceptions.py`: Standard domain exceptions (`DomainException`, `NotFoundError`, `UnauthorizedError`).
- `app/mcp/repositories/`: Folder containing database query orchestrations (`job_repo.py`, `app_repo.py`, `task_repo.py`, `memory_repo.py`).
- `app/mcp/services/`: Folder containing business orchestration logic (`job_service.py`, `app_service.py`, `profile_service.py`).
- `app/mcp/di.py`: Reusable dependency providers for database sessions and current authenticated user.

## Proposed Changes

### 1. Centralized Domain Exceptions (`app/mcp/exceptions.py`)
- Define base class `DomainException` and standard subclasses.
- Write `@translate_mcp_exceptions` decorator to catch and serialize domain exceptions to `ErrorResponse` DTO structures.

### 2. Dependency Providers (`app/mcp/di.py`)
- Provide constructor context managers to retrieve scoped SQLAlchemy sessions.
- Expose user identity verification functions that extract context variables safely.

### 3. Repository Layer (`app/mcp/repositories/`)
- Extract query definitions out of tool routes.
- Implement specialized repository classes (e.g., `JobRepository`, `ApplicationRepository`) that accept `AsyncSession`.

### 4. Service Layer (`app/mcp/services/`)
- Implement business logic handlers (e.g., `JobService`, `ApplicationService`).
- Inject relevant repositories and validate tenant permissions on application requests.

### 5. Transport Layer (`app/mcp/mcp_server.py`)
- Clean `mcp_server.py` to only contain FastMCP registrations.
- Extract authentication context, initialize services, and return mapped response schemas.

## Verification Plan

### Automated Tests
- Test exception translation decorators.
- Test service layers using mocked repositories.
- Test endpoint integrations using a mock HTTP/SSE client.
