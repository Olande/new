from __future__ import annotations

import datetime
import uuid

from app.core.db.models.agent_task import AgentTask
from app.core.db.models.application import Application
from app.mcp.di import AuthenticatedUser
from app.mcp.exceptions import NotFoundError, UnauthorizedError, ValidationError
from app.mcp.mcp_schemas import ConfirmSubmissionOutput, SubmitApplicationOutput
from app.mcp.repositories.app_repo import ApplicationRepository
from app.mcp.repositories.job_repo import JobRepository
from app.mcp.repositories.task_repo import AgentTaskRepository


class SubmissionService:
    def __init__(
        self,
        task_repo: AgentTaskRepository,
        app_repo: ApplicationRepository,
        job_repo: JobRepository,
    ):
        self.task_repo = task_repo
        self.app_repo = app_repo
        self.job_repo = job_repo

    async def submit_application(
        self,
        user: AuthenticatedUser,
        job_id: uuid.UUID,
        application_id: uuid.UUID | None = None,
    ) -> SubmitApplicationOutput:
        """Creates a pending agent task for application submission, requiring manual confirmation."""
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")

        app_obj = None
        if application_id:
            app_obj = await self.app_repo.get_by_id(application_id)
            if not app_obj or str(app_obj.user_id) != str(user.user_id):
                raise NotFoundError(
                    f"Application draft {application_id} not found or not owned"
                )
        else:
            app_obj = await self.app_repo.get_latest_for_user_and_job(
                user.user_id, job_id
            )
            if not app_obj:
                app_obj = Application(
                    user_id=user.user_id, job_id=job_id, status="draft"
                )
                await self.app_repo.create(app_obj)

        task = AgentTask(
            thread_id=f"submit-{user.user_id}-{job_id}",
            graph_name="submit_application",
            status="pending",
            payload={
                "action": "submit_application",
                "job_id": str(job_id),
                "application_id": str(app_obj.id),
                "user_id": str(user.user_id),
                "preview": {
                    "job_title": job.title,
                    "company": job.company_name,
                    "application_id": str(app_obj.id),
                    "resume_present": bool(app_obj.resume_draft),
                },
            },
        )
        await self.task_repo.create(task)

        return SubmitApplicationOutput(
            needs_approval=True,
            task_id=str(task.id),
            job_id=str(job_id),
            application_id=str(app_obj.id),
            preview=task.payload["preview"],
            message=f"Approval required for {job.title} at {job.company_name}. Call confirm_submission_tool.",
        )

    async def confirm_submission(
        self,
        user: AuthenticatedUser,
        task_id: uuid.UUID,
        approved: bool,
    ) -> ConfirmSubmissionOutput:
        """Confirms or cancels a pending application submission, updating database states and checking ownership."""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task {task_id} not found")

        if task.payload.get("user_id") and str(task.payload["user_id"]) != str(
            user.user_id
        ):
            raise UnauthorizedError("Cross-tenant blocked")

        if task.status != "pending":
            raise ValidationError(f"Task already {task.status}")

        job_id = uuid.UUID(task.payload["job_id"])
        app_id = uuid.UUID(task.payload["application_id"])

        if not approved:
            task.status = "cancelled"
            task.completed_at = datetime.datetime.now(datetime.UTC)
            return ConfirmSubmissionOutput(
                status="cancelled",
                application_id=str(app_id),
                job_id=str(job_id),
                message="Cancelled, draft kept.",
            )

        app_obj = await self.app_repo.get_by_id(app_id)
        if not app_obj or str(app_obj.user_id) != str(user.user_id):
            raise NotFoundError("App not found/forbidden")

        app_obj.status = "submitted"
        task.status = "completed"
        task.result = {
            "application_id": str(app_id),
            "job_id": str(job_id),
            "submitted_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        task.completed_at = datetime.datetime.now(datetime.UTC)

        return ConfirmSubmissionOutput(
            status="submitted",
            application_id=str(app_id),
            job_id=str(job_id),
            message=f"Application {app_id} submitted.",
        )
