"""FastMCP Server for Postgres-backed Job platform."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core.config.settings import settings as app_settings
from app.core.jdl.client import JobDataLakeClient
from app.mcp.di import require_user
from app.mcp.exceptions import translate_mcp_exceptions
from app.mcp.factory import with_service
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
from app.mcp.services.job_fallback_service import JobFallbackService
from app.mcp.services.job_service import JobService
from app.mcp.services.profile_service import ProfileService
from app.mcp.services.submission_service import SubmissionService

logger = logging.getLogger("mcp")

mcp = FastMCP("careerpilot-jobs-postgres")


def _build_fallback_service(session) -> JobFallbackService | None:
    """Build a JobFallbackService if the JDL API key is configured."""
    if not app_settings.job_data_lake_api_key:
        return None
    try:
        jdl_client = JobDataLakeClient(api_key=app_settings.job_data_lake_api_key)
        return JobFallbackService(
            job_repo=JobRepository(session),
            jdl_client=jdl_client,
            settings=app_settings,
        )
    except ValueError:
        logger.warning("JDL fallback disabled: JobDataLakeClient init failed")
        return None


@mcp.tool(
    description="Search machine learning / software engineering jobs. Returns hybrid-search scores."
)
@translate_mcp_exceptions
async def search_jobs_tool(
    query: str, limit: int = 10, cosine_threshold: float = 0.5
) -> dict[str, Any]:
    inp = SearchJobsInput(query=query, limit=limit, cosine_threshold=cosine_threshold)
    return await with_service(
        lambda s: JobService(
            JobRepository(s),
            fallback_service=_build_fallback_service(s),
            settings=app_settings,
        ),
        lambda svc: svc.search_jobs(
            query=inp.query, limit=inp.limit, cosine_threshold=inp.cosine_threshold
        ).model_dump(),
    )


@mcp.tool(
    description="Retrieve full job details. Includes complete untruncated description text."
)
@translate_mcp_exceptions
async def get_job_tool(job_id: str) -> dict[str, Any]:
    inp = GetJobInput(job_id=uuid.UUID(job_id))
    return await with_service(
        lambda s: JobService(
            JobRepository(s),
            fallback_service=_build_fallback_service(s),
            settings=app_settings,
        ),
        lambda svc: svc.get_job(inp.job_id).model_dump(),
    )


@mcp.tool(
    description="Retrieve authenticated user profile and career memories (Postgres Store/legacy fallback). Auth required."
)
@translate_mcp_exceptions
async def get_my_profile_tool() -> dict[str, Any]:
    user = require_user()
    return await with_service(
        lambda s: ProfileService(UserRepository(s), CareerMemoryRepository(s)),
        lambda svc: svc.get_profile(user).model_dump(),
    )


@mcp.tool(
    description="Create draft application. Auth required. Draft only, not submitted."
)
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
    return await with_service(
        lambda s: ApplicationService(ApplicationRepository(s), JobRepository(s)),
        lambda svc: svc.create_draft(
            user=user,
            job_id=inp.job_id,
            resume_draft=inp.resume_draft,
            cover_letter_draft=inp.cover_letter_draft,
            notes=inp.notes,
        ).model_dump(),
    )


@mcp.tool(
    description="Submit application - high-risk. Creates pending AgentTask and requires confirm_submission_tool."
)
@translate_mcp_exceptions
async def submit_application_tool(
    job_id: str, application_id: str | None = None
) -> dict[str, Any]:
    inp = SubmitApplicationInput(
        job_id=uuid.UUID(job_id),
        application_id=uuid.UUID(application_id) if application_id else None,
    )
    user = require_user()
    return await with_service(
        lambda s: SubmissionService(
            AgentTaskRepository(s), ApplicationRepository(s), JobRepository(s)
        ),
        lambda svc: svc.submit_application(
            user=user,
            job_id=inp.job_id,
            application_id=inp.application_id,
        ).model_dump(),
    )


@mcp.tool(
    description="Confirm/cancel pending submission. Second step of HIL. Enforces tenant isolation."
)
@translate_mcp_exceptions
async def confirm_submission_tool(task_id: str, approved: bool) -> dict[str, Any]:
    inp = ConfirmSubmissionInput(task_id=uuid.UUID(task_id), approved=approved)
    user = require_user()
    return await with_service(
        lambda s: SubmissionService(
            AgentTaskRepository(s), ApplicationRepository(s), JobRepository(s)
        ),
        lambda svc: svc.confirm_submission(
            user=user,
            task_id=inp.task_id,
            approved=inp.approved,
        ).model_dump(),
    )


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
                        set_request_context(
                            user_id=str(claims["user_id"]),
                            tenant_id=claims.get("tenant_id"),
                        )
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
