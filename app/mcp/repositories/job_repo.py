from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.job import Job, JobDescription, JobSource
from app.core.jdl.schemas import JobCreate
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
        return await core_search_jobs(
            self.session,
            query,
            cosine_distance_threshold=cosine_threshold,
            result_limit=limit,
        )

    async def upsert_from_fallback(self, jobs: list[JobCreate]) -> list[Job]:
        """Bulk-upsert fallback jobs via ON CONFLICT (dedup_hash) DO UPDATE.

        Populates both jobs and job_sources tables for provenance tracking.
        On conflict, refreshes job metadata fields and sets fallback_source='jdl_api'.
        """
        if not jobs:
            return []

        now = datetime.now(UTC)
        job_rows = []
        source_rows = []
        for j in jobs:
            job_id = uuid.uuid4()
            vals = j.model_dump(exclude={"source"})
            vals.update(
                {"id": job_id, "fallback_source": "jdl_api", "last_seen_at": now}
            )
            job_rows.append(vals)
            source_rows.append(
                {
                    "job_id": job_id,
                    "source_name": j.source.source_name,
                    "source_job_id": j.source.source_job_id,
                    "source_url": j.source.source_url,
                    "first_seen_at": j.source.first_seen_at,
                }
            )

        pg_ins = pg_insert(Job).values(job_rows)
        upsert_stmt = pg_ins.on_conflict_do_update(
            index_elements=["dedup_hash"],
            set_={
                "fallback_source": "jdl_api",
                "last_seen_at": now,
                "title": pg_ins.excluded.title,
                "company_name": pg_ins.excluded.company_name,
                "domain_name": pg_ins.excluded.domain_name,
                "role": pg_ins.excluded.role,
                "job_function": pg_ins.excluded.job_function,
                "seniority": pg_ins.excluded.seniority,
                "employment_type": pg_ins.excluded.employment_type,
                "remote_type": pg_ins.excluded.remote_type,
                "locations": pg_ins.excluded.locations,
                "countries": pg_ins.excluded.countries,
                "required_skills": pg_ins.excluded.required_skills,
                "employee_count": pg_ins.excluded.employee_count,
                "funding": pg_ins.excluded.funding,
            },
        ).returning(Job)
        result = await self.session.execute(upsert_stmt)
        upserted = list(result.scalars().all())

        # Upsert sources (ignore conflict — source already exists from a previous fetch)
        if source_rows:
            src_stmt = (
                pg_insert(JobSource)
                .values(source_rows)
                .on_conflict_do_nothing(index_elements=["source_name", "source_job_id"])
            )
            await self.session.execute(src_stmt)

        return upserted

    async def get_by_source_job_id(
        self,
        source_job_id: str,
        source_name: str = "jobdatalake",
    ) -> Job | None:
        """Look up a job by its external source ID via the job_sources join table."""
        stmt = (
            select(Job)
            .join(JobSource, JobSource.job_id == Job.id)
            .where(
                JobSource.source_name == source_name,
                JobSource.source_job_id == source_job_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
