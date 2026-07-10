# Implementation Plan: MCP Server

**Branch**: `phase4-infra-decoupling` | **Status**: Migrated | **Spec**: `specs/009-mcp-server/spec.md`

## Summary

Implement a Model Context Protocol (MCP) server exposing 5 tools for job search, application management, and user profiles. Uses FastMCP with SSE (HTTP) and stdio transports, with JWT-based authentication, tenant isolation middleware, and a repository/service architecture.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: `mcp[fastmcp]` (MCP protocol), `starlette` (ASGI middleware), `PyJWT` (token parsing), `pydantic` (schemas)
**Storage**: PostgreSQL via SQLAlchemy async (5 repositories)
**Testing**: ✅ Partial — `tests/test_mcp.py` covers tool endpoints
**Pattern**: Repository → Service → FastMCP tool (controller)

## Architecture

```
[Client] ↔ SSE/stdio ↔ FastMCP Server
                            │
                    TenantMiddleware (JWT → context)
                            │
                    ┌───────┴───────┐
                    │  Tool Layer    │
                    │  (5 tools)     │
                    └───────┬───────┘
                            │
                    ┌───────┴───────┐
                    │ Service Layer  │
                    │ (4 services)   │
                    └───────┬───────┘
                            │
                    ┌───────┴───────┐
                    │ Repository    │
                    │ Layer (5)     │
                    └───────┬───────┘
                            │
                    ┌───────┴───────┐
                    │  PostgreSQL   │
                    └───────────────┘
```

## MCP Tools

| Tool | Input | Output | Auth | Service |
|------|-------|--------|------|---------|
| `search_jobs_tool` | query, limit, threshold | SearchJobsOutput (hits + total) | No | JobService |
| `get_job_tool` | job_id (UUID) | JobDetailOutput | No | JobService |
| `get_my_profile_tool` | — | GetProfileOutput | Yes | ProfileService |
| `create_application_draft_tool` | job_id, resume, cover_letter, notes | CreateApplicationOutput | Yes | ApplicationService |
| `submit_application_tool` | job_id, application_id | SubmitApplicationOutput | Yes | SubmissionService |
| `confirm_submission_tool` | task_id, approved | ConfirmSubmissionOutput | Yes | SubmissionService |

## Repository/Service Map

| Repository | Methods | Service |
|------------|---------|---------|
| `JobRepository` | `search_jobs()`, `get_job()` | `JobService` |
| `ApplicationRepository` | `create_draft()`, `get_by_user_and_job()` | `ApplicationService` |
| `UserRepository` | `get_by_id()` | `ProfileService` |
| `CareerMemoryRepository` | `get_by_user_id()` | `ProfileService` |
| `AgentTaskRepository` | `create()`, `update_status()` | `SubmissionService` |

## Key Patterns

1. **Dependency injection**: `db_session_scope()` context manager provides per-request session; `require_user()` extracts authenticated user from request context
2. **Exception translation**: `@translate_mcp_exceptions` decorator catches domain exceptions → structured `ErrorResponse`
3. **Request context**: `TenantMiddleware` extracts JWT claims → `request_context` (ContextVar) for user_id / tenant_id
4. **Human-in-the-loop**: Submission creates `AgentTask` with pending status; `confirm_submission_tool` completes or cancels it
