---
description: "Task list for MCP Server — all tasks completed (migrated)"
---

# Tasks: MCP Server

**Status**: All tasks [x] completed (migrated from existing codebase)

## Phase 1: Foundation & Schemas

- [x] T001 Create Pydantic input/output schemas (`app/mcp/mcp_schemas.py`): 12 models for tool I/O
- [x] T02 Create exception hierarchy (`app/mcp/exceptions.py`): `DomainException` base + `NotFoundError`, `UnauthorizedError`, `ValidationError`
- [x] T03 Implement `translate_mcp_exceptions` decorator for consistent error handling
- [x] T04 Implement request context (`app/mcp/mcp_context.py`): ContextVar-based user_id/tenant_id with JWT extraction

## Phase 2: Repositories

- [x] T05 Create `JobRepository` (`app/mcp/repositories/job_repo.py`): `search_jobs()`, `get_job()` with description eager loading
- [x] T06 Create `ApplicationRepository` (`app/mcp/repositories/app_repo.py`): `create_draft()`, `get_by_user_and_job()`
- [x] T07 Create `UserRepository` (`app/mcp/repositories/user_repo.py`): `get_by_id()`
- [x] T08 Create `CareerMemoryRepository` (`app/mcp/repositories/memory_repo.py`): `get_by_user_id()`
- [x] T09 Create `AgentTaskRepository` (`app/mcp/repositories/task_repo.py`): `create()`, `update_status()`
- [x] T10 Implement DI helpers (`app/mcp/di.py`): `db_session_scope()`, `require_user()`

## Phase 3: Services

- [x] T11 Create `JobService` (`app/mcp/services/job_service.py`): orchestrates hybrid search, returns `SearchJobsOutput` / `JobDetailOutput`
- [x] T12 Create `ApplicationService` (`app/mcp/services/app_service.py`): draft creation with dedup check
- [x] T13 Create `ProfileService` (`app/mcp/services/profile_service.py`): user profile + career memory composition
- [x] T14 Create `SubmissionService` (`app/mcp/services/submission_service.py`): two-phase HIL submission flow with AgentTask

## Phase 4: MCP Server Wiring

- [x] T15 Create FastMCP server (`app/mcp/mcp_server.py`): register `search_jobs_tool`
- [x] T16 Register `get_job_tool` with job detail lookup
- [x] T17 Register `get_my_profile_tool` with auth requirement
- [x] T18 Register `create_application_draft_tool` with draft creation
- [x] T19 Register `submit_application_tool` and `confirm_submission_tool` with HIL flow
- [x] T20 Create ASGI app factory (`create_asgi_app()`) with `TenantMiddleware` for JWT auth

## Phase 5: Tests

- [x] T21 Write `tests/test_mcp.py` with tool endpoint tests (4 tools covered)
- [x] T22 Test exception translation for domain errors

## Gaps Identified

| Gap | Type | Recommendation |
|-----|------|----------------|
| ⚠️ No JWT signature validation | Security | Middleware extracts claims but doesn't verify token signature — assumes upstream validation |
| ⚠️ Generic Exception catch in `translate_mcp_exceptions` | Error handling | Line 60-64 catches all `Exception` — consider logging context for debugging |
| ℹ️ `search_jobs_tool` has no pagination | UX | Consider adding offset/cursor for large result sets |
