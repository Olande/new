from __future__ import annotations

import uuid

from app.core.db.models.application import Application
from app.mcp.di import AuthenticatedUser
from app.mcp.exceptions import NotFoundError
from app.mcp.mcp_schemas import CreateApplicationOutput
from app.mcp.repositories.app_repo import ApplicationRepository
from app.mcp.repositories.job_repo import JobRepository


class ApplicationService:
    def __init__(self, app_repo: ApplicationRepository, job_repo: JobRepository):
        self.app_repo = app_repo
        self.job_repo = job_repo

    async def create_draft(
        self,
        user: AuthenticatedUser,
        job_id: uuid.UUID,
        resume_draft: str | None = None,
        cover_letter_draft: str | None = None,
        notes: str | None = None,
    ) -> CreateApplicationOutput:
        """Creates a new application draft for a user and job."""
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")

        app_row = Application(
            user_id=user.user_id,
            job_id=job_id,
            status="draft",
            resume_draft=resume_draft,
            cover_letter_draft=cover_letter_draft,
            notes=notes,
        )
        await self.app_repo.create(app_row)
        return CreateApplicationOutput(
            application_id=str(app_row.id),
            job_id=str(job.id),
            status=app_row.status,
        )
