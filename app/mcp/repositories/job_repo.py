from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.job import Job, JobDescription
from app.retrieval.hybrid_search import search_jobs as core_search_jobs


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        """Retrieves a job by its unique UUID."""
        return await self.session.get(Job, job_id)

    async def get_description(self, job_id: uuid.UUID) -> JobDescription | None:
        """Retrieves the full job description associated with a job."""
        q = await self.session.execute(
            select(JobDescription).where(JobDescription.job_id == job_id)
        )
        return q.scalar_one_or_none()

    async def search(self, query: str, limit: int, cosine_threshold: float) -> list:
        """Searches jobs using hybrid search algorithms."""
        return await core_search_jobs(query, limit=limit, cosine_threshold=cosine_threshold)
