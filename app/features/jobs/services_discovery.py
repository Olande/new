import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.settings import settings
from app.features.jobs.repository import close_stale_jobs, upsert_job, upsert_job_source
from app.features.jobs.schemas import JobSearchCriteria
from app.features.jobs.services_client import JobDataLakeClient
from app.features.jobs.services_normalization import normalize_job

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


async def run_discovery(
    db: AsyncSession,
    criteria: JobSearchCriteria,
    source_name: str,
    page_cap: int | None = None,
    unconfirmed_limit: int = 2,
    client: JobDataLakeClient | None = None,
) -> DiscoveryResult:
    result = DiscoveryResult()
    seen_source_job_ids: set[str] = set()

    async def process_stream(jdl_client) -> None:
        async for raw_job in jdl_client.search_all_results(
            criteria, per_page=settings.discovery_per_page, page_cap=page_cap
        ):
            try:
                normalized = normalize_job(raw_job, source_name=source_name)
            except Exception:
                logger.warning("failed to normalize job, skipping", exc_info=True)
                continue

            now_utc = datetime.now(UTC)
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

    result.jobs_closed = await close_stale_jobs(
        db, source_name, seen_source_job_ids, unconfirmed_limit
    )

    await db.commit()

    try:
        from app.core.llm.embeddings import refresh_stale_embeddings

        logger.info("Refreshing stale job embeddings after discovery...")
        await refresh_stale_embeddings(db)
    except Exception as e:
        logger.error(f"Failed to refresh stale embeddings: {e}", exc_info=True)

    return result
