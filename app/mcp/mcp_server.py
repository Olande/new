"""
FastMCP Server for Postgres-backed Job platform.
Acts as a thin transport layer, delegating to services & repositories.
Centralized authentication and error handling are enforced.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.di import db_session_scope, require_user
from app.mcp.exceptions import translate_mcp_exceptions
from app.mcp.mcp_context import (
    clear_request_context,
    extract_context_from_jwt,
    set_request_context,
)
from app.mcp.mcp_schemas import (
    ConfirmSubmissionInput,
    CreateApplicationInput,
    GetJobInput,
    SearchJobsInput,
    SubmitApplicationInput,
)
from app.mcp.repositories.app_repo import ApplicationRepository
from app.mcp.repositories.job_repo import JobRepository
from app.mcp.repositories.memory_repo import CareerMemoryRepository
from app.mcp.repositories.task_repo import AgentTaskRepository
from app.mcp.repositories.user_repo import UserRepository
from app.mcp.services.app_service import ApplicationService
from app.mcp.services.job_service import JobService
from app.mcp.services.profile_service import ProfileService
from app.mcp.services.submission_service import SubmissionService

logger = logging.getLogger("mcp")

# Primary FastMCP instance
mcp = FastMCP("careerpilot-jobs-postgres")


@mcp.tool(description="Search machine learning / software engineering jobs. Returns hybrid-search scores.")
@translate_mcp_exceptions
async def search_jobs_tool(query: str, limit: int = 10, cosine_threshold: float = 0.5) -> dict[str, Any]:
    # Input validation via Pydantic DTO
    inp = SearchJobsInput(query=query, limit=limit, cosine_threshold=cosine_threshold)
    async with db_session_scope() as session:
        job_repo = JobRepository(session)
        job_service = JobService(job_repo)
        res = await job_service.search_jobs(
            query=inp.query,
            limit=inp.limit,
            cosine_threshold=inp.cosine_threshold,
        )
        return res.model_dump()


@mcp.tool(description="Retrieve full job details. Includes complete untruncated description text.")
@translate_mcp_exceptions
async def get_job_tool(job_id: str) -> dict[str, Any]:
    inp = GetJobInput(job_id=uuid.UUID(job_id))
    async with db_session_scope() as session:
        job_repo = JobRepository(session)
        job_service = JobService(job_repo)
        res = await job_service.get_job(inp.job_id)
        return res.model_dump()


@mcp.tool(description="Retrieve authenticated user profile and career memories (Postgres Store/legacy fallback). Auth required.")
@translate_mcp_exceptions
async def get_my_profile_tool() -> dict[str, Any]:
    user = require_user()
    async with db_session_scope() as session:
        user_repo = UserRepository(session)
        memory_repo = CareerMemoryRepository(session)
        profile_service = ProfileService(user_repo, memory_repo)
        res = await profile_service.get_profile(user)
        return res.model_dump()


@mcp.tool(description="Create draft application. Auth required. Draft only, not submitted.")
@translate_mcp_exceptions
async def create_application_draft_tool(
    job_id: str,
    resume_draft: str | None = None,
    cover_letter_draft: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    inp = CreateApplicationInput(
        job_id=uuid.UUID(job_id),
        resume_draft=resume_draft,
        cover_letter_draft=cover_letter_draft,
        notes=notes,
    )
    user = require_user()
    async with db_session_scope() as session:
        job_repo = JobRepository(session)
        app_repo = ApplicationRepository(session)
        app_service = ApplicationService(app_repo, job_repo)
        res = await app_service.create_draft(
            user=user,
            job_id=inp.job_id,
            resume_draft=inp.resume_draft,
            cover_letter_draft=inp.cover_letter_draft,
            notes=inp.notes,
        )
        return res.model_dump()


@mcp.tool(description="Submit application - high-risk. Creates pending AgentTask and requires confirm_submission_tool.")
@translate_mcp_exceptions
async def submit_application_tool(job_id: str, application_id: str | None = None) -> dict[str, Any]:
    inp = SubmitApplicationInput(
        job_id=uuid.UUID(job_id),
        application_id=uuid.UUID(application_id) if application_id else None,
    )
    user = require_user()
    async with db_session_scope() as session:
        job_repo = JobRepository(session)
        app_repo = ApplicationRepository(session)
        task_repo = AgentTaskRepository(session)
        submission_service = SubmissionService(task_repo, app_repo, job_repo)
        res = await submission_service.submit_application(
            user=user,
            job_id=inp.job_id,
            application_id=inp.application_id,
        )
        return res.model_dump()


@mcp.tool(description="Confirm/cancel pending submission. Second step of HIL. Enforces tenant isolation.")
@translate_mcp_exceptions
async def confirm_submission_tool(task_id: str, approved: bool) -> dict[str, Any]:
    inp = ConfirmSubmissionInput(task_id=uuid.UUID(task_id), approved=approved)
    user = require_user()
    async with db_session_scope() as session:
        job_repo = JobRepository(session)
        app_repo = ApplicationRepository(session)
        task_repo = AgentTaskRepository(session)
        submission_service = SubmissionService(task_repo, app_repo, job_repo)
        res = await submission_service.confirm_submission(
            user=user,
            task_id=inp.task_id,
            approved=inp.approved,
        )
        return res.model_dump()


def create_asgi_app():
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        app = mcp.sse_app()
        class TenantMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                auth = request.headers.get("authorization", "")
                if auth:
                    claims = extract_context_from_jwt(auth)
                    if claims.get("user_id"):
                        set_request_context(user_id=str(claims["user_id"]), tenant_id=claims.get("tenant_id"))
                try:
                    return await call_next(request)
                finally:
                    clear_request_context()
        app.add_middleware(TenantMiddleware)
        return app
    except Exception:
        return mcp


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
