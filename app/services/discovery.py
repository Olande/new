import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models.job import Job
from app.db.models.job_source import JobSource
from app.schemas.job import JobSearchCriteria
from app.services.job_data_lake_client import JobDataLakeClient
from app.services.normalization import normalize_job
from app.config.settings import settings

logger = logging.getLogger(__name__)


class DiscoveryResult:
    __slots__ = (
        "pages_crawled",
        "jobs_created",
        "jobs_updated",
        "jobs_closed",
        "job_ids",
    )

    def __init__(
        self,
        pages_crawled: int = 0,
        jobs_created: int = 0,
        jobs_updated: int = 0,
        jobs_closed: int = 0,
        job_ids: list[str] | None = None,
    ) -> None:
        self.pages_crawled = pages_crawled
        self.jobs_created = jobs_created
        self.jobs_updated = jobs_updated
        self.jobs_closed = jobs_closed
        self.job_ids: list[str] = job_ids or []


async def upsert_job(
    db: AsyncSession, normalized, now_utc: datetime
) -> tuple[Job, bool]:
    """Upsert a Job by dedup_hash. Returns (job, created)."""
    values = {
        "dedup_hash": normalized.dedup_hash,
        "title": normalized.title,
        "company_name": normalized.company_name,
        "domain_name": normalized.domain_name,
        "role": normalized.role,
        "job_function": normalized.job_function,
        "seniority": normalized.seniority,
        "employment_type": normalized.employment_type,
        "remote_type": normalized.remote_type,
        "locations": normalized.locations,
        "countries": normalized.countries,
        "required_skills": normalized.required_skills,
        "employee_count": normalized.employee_count,
        "funding": normalized.funding,
        "status": "active",
        "posted_at": normalized.posted_at,
        "last_seen_at": now_utc,
    }

    from sqlalchemy import text
    stmt = pg_insert(Job).values(**values).on_conflict_do_update(
        index_elements=['dedup_hash'],
        set_={"last_seen_at": now_utc, "status": "active"}
    ).returning(Job, text("xmax = 0 AS is_inserted"))

    res = await db.execute(stmt)
    row = res.one()
    job, is_inserted = row[0], row[1]

    return job, is_inserted


async def upsert_job_source(
    db: AsyncSession, job: Job, normalized, now_utc: datetime
) -> None:
    """Upsert a JobSource by (source_name, source_job_id)."""
    stmt = select(JobSource).where(
        JobSource.source_name == normalized.source.source_name,
        JobSource.source_job_id == normalized.source.source_job_id,
    )
    source = (await db.execute(stmt)).scalar_one_or_none()

    if source is None:
        db.add(
            JobSource(
                job_id=job.id,
                source_name=normalized.source.source_name,
                source_job_id=normalized.source.source_job_id,
                source_url=normalized.source.source_url,
                first_seen_at=normalized.source.first_seen_at,
                last_checked_at=now_utc,
                unconfirmed_count=0,
            )
        )
    else:
        source.last_checked_at = now_utc
        source.unconfirmed_count = 0


async def close_stale_jobs(
    db: AsyncSession,
    source_name: str,
    seen_source_job_ids: set[str],
    unconfirmed_limit: int,
    result: DiscoveryResult,
) -> None:
    """Increment miss count on untouched sources and close jobs where every
    source has exceeded the unconfirmed threshold.
    """
    stmt_unseen = select(JobSource).where(JobSource.source_name == source_name)
    if seen_source_job_ids:
        stmt_unseen = stmt_unseen.where(
            JobSource.source_job_id.not_in(seen_source_job_ids)
        )

    unseen_sources = (await db.execute(stmt_unseen)).scalars().all()
    if not unseen_sources:
        return

    jobs_to_check: set = set()
    for src in unseen_sources:
        src.unconfirmed_count += 1
        jobs_to_check.add(src.job_id)

    stmt_all_srcs = select(JobSource).where(JobSource.job_id.in_(jobs_to_check))
    all_srcs = (await db.execute(stmt_all_srcs)).scalars().all()

    srcs_by_job: dict = {}
    for s in all_srcs:
        srcs_by_job.setdefault(s.job_id, []).append(s)

    jobs_to_close = [
        job_id
        for job_id, srcs in srcs_by_job.items()
        if all(s.unconfirmed_count >= unconfirmed_limit for s in srcs)
    ]

    if not jobs_to_close:
        return

    stmt_jobs = select(Job).where(Job.id.in_(jobs_to_close), Job.status != "closed")
    jobs = (await db.execute(stmt_jobs)).scalars().all()
    for job in jobs:
        job.status = "closed"
        result.jobs_closed += 1


async def discover_jobs(
    db: AsyncSession,
    criteria: JobSearchCriteria,
    source_name: str = "job_data_lake",
    page_cap: int | None = None,
    unconfirmed_limit: int | None = None,
    *,
    client: JobDataLakeClient | None = None,
) -> DiscoveryResult:

    page_cap = page_cap or settings.discovery_page_cap
    unconfirmed_limit = unconfirmed_limit or settings.discovery_unconfirmed_limit
    result = DiscoveryResult()
    seen_source_job_ids: set[str] = set()

    async def process_stream(jdl_client: JobDataLakeClient) -> None:
        async for raw_job in jdl_client.search_all_results(
            criteria, per_page=settings.discovery_per_page, page_cap=page_cap
        ):
            try:
                normalized = normalize_job(raw_job, source_name=source_name)
            except Exception:
                logger.warning("failed to normalize job, skipping", exc_info=True)
                continue

            now_utc = datetime.now(timezone.utc)
            job, created = await upsert_job(db, normalized, now_utc)
            if created:
                result.jobs_created += 1
            else:
                result.jobs_updated += 1

            await upsert_job_source(db, job, normalized, now_utc)
            result.job_ids.append(str(job.id))
            seen_source_job_ids.add(normalized.source.source_job_id)

    if client is not None:
        await process_stream(client)
    else:
        async with JobDataLakeClient(
            api_key=settings.job_data_lake_api_key
        ) as jdl_client:
            await process_stream(jdl_client)

    await close_stale_jobs(
        db, source_name, seen_source_job_ids, unconfirmed_limit, result
    )

    await db.commit()

    try:
        from app.retrieval.embeddings import refresh_stale_embeddings

        logger.info("Refreshing stale job embeddings after discovery...")
        await refresh_stale_embeddings(db)
    except Exception as e:
        logger.error(f"Failed to refresh stale embeddings: {e}", exc_info=True)

    return result
