from __future__ import annotations

import uuid

from app.core.config.settings import Settings
from app.mcp.exceptions import NotFoundError
from app.mcp.mcp_schemas import JobDetailOutput, JobHit, SearchJobsOutput
from app.mcp.repositories.job_repo import JobRepository
from app.mcp.services.job_fallback_service import JobFallbackService


class JobService:
    def __init__(
        self,
        job_repo: JobRepository,
        fallback_service: JobFallbackService | None = None,
        settings: Settings | None = None,
    ):
        self.job_repo = job_repo
        self.fallback_service = fallback_service
        self.settings = settings

    async def search_jobs(
        self, query: str, limit: int, cosine_threshold: float
    ) -> SearchJobsOutput:
        """Search jobs with automatic fallback to JDL API when DB is sparse."""
        if self.fallback_service is not None and self.settings is not None:
            criteria = {"query": query}
            return await self.fallback_service.search_with_fallback(
                query=query,
                limit=limit,
                threshold=self.settings.fallback_min_result_threshold,
                criteria=criteria,
            )
        # Standard DB-only path when fallback is not configured
        hits = await self.job_repo.search(
            query, limit=limit, cosine_threshold=cosine_threshold
        )
        job_hits = [
            JobHit(
                id=str(h.id),
                title=h.title,
                company_name=h.company_name,
                required_skills=list(h.required_skills or []),
                remote_type=h.remote_type,
                locations=list(h.locations or []),
                score=h.rrf_score,
            )
            for h in hits
        ]
        return SearchJobsOutput(hits=job_hits, total=len(job_hits))

    async def get_job(self, job_id: uuid.UUID) -> JobDetailOutput:
        """Get a single job by ID with JDL API fallback."""
        if self.fallback_service is not None:
            result = await self.fallback_service.get_job_with_fallback(job_id)
            if result is not None:
                return result

        # Standard DB-only path
        job = await self.job_repo.get_by_id(job_id)
        if not job or job.status != "active":
            raise NotFoundError(f"Job {job_id} not found or inactive")

        desc = await self.job_repo.get_description(job_id)
        return JobDetailOutput(
            id=str(job.id),
            title=job.title,
            company_name=job.company_name,
            description=desc.cleaned_text if desc else "",
            required_skills=list(job.required_skills or []),
            locations=list(job.locations or []),
            remote_type=job.remote_type,
            employment_type=job.employment_type,
            seniority=list(job.seniority or []),
            fallback_source=job.fallback_source,
        )
