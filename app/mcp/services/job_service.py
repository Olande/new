from __future__ import annotations

import uuid

from app.mcp.exceptions import NotFoundError
from app.mcp.mcp_schemas import JobDetailOutput, JobHit, SearchJobsOutput
from app.mcp.repositories.job_repo import JobRepository


class JobService:
    def __init__(self, job_repo: JobRepository):
        self.job_repo = job_repo

    async def search_jobs(self, query: str, limit: int, cosine_threshold: float) -> SearchJobsOutput:
        """Orchestrates job searching and maps database hits to DTO schemas."""
        hits = await self.job_repo.search(query, limit=limit, cosine_threshold=cosine_threshold)
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
        """Retrieves active job details, failing with NotFoundError if missing or inactive."""
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
        )
