import asyncio
import uuid
from itertools import batched

import httpx
from aiolimiter import AsyncLimiter
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.db.models.job import Job, JobDescription, JobSource

JINA_PREFIX = "https://r.jina.ai/"

MAX_CONCURRENT_REQUESTS = 3
REQUESTS_PER_SECOND = 2

semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
limiter = AsyncLimiter(REQUESTS_PER_SECOND, 1)


@retry(
    retry=retry_if_exception_type(
        (
            httpx.HTTPStatusError,
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
        )
    ),
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=2, max=60),
    reraise=True,
)
async def fetch_jina_content(
    client: httpx.AsyncClient,
    source_url: str,
) -> str:
    jina_url = f"{JINA_PREFIX}{source_url}"

    async with semaphore, limiter:
        response = await client.get(jina_url)

    if response.status_code == 429:
        logger.warning("Rate limited by Jina: %s", source_url)
        response.raise_for_status()

    response.raise_for_status()

    return response.text


async def populate_job_descriptions(
    db: AsyncSession,
    batch_size: int = 10,
    job_ids: list[str] | None = None,
) -> None:
    stmt = (
        select(
            Job.id,
            JobSource.source_url,
        )
        .join(JobSource, JobSource.job_id == Job.id)
        .outerjoin(
            JobDescription,
            JobDescription.job_id == Job.id,
        )
        .where(JobDescription.job_id.is_(None))
        .distinct(Job.id)
    )

    if job_ids:
        uuids = [uuid.UUID(jid) for jid in job_ids]
        stmt = stmt.where(Job.id.in_(uuids))

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        logger.info("No jobs require description fetching")
        return

    logger.info("Found %d jobs requiring descriptions", len(rows))

    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
    ) as client:
        for batch in batched(rows, batch_size, strict=False):
            tasks = [
                fetch_jina_content(client, source_url) for job_id, source_url in batch
            ]

            responses = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            descriptions = []

            for (job_id, source_url), response in zip(batch, responses, strict=False):
                if isinstance(response, Exception):
                    logger.warning(
                        "Failed fetching job %s (%s): %s",
                        job_id,
                        source_url,
                        response,
                    )
                    continue

                descriptions.append(
                    JobDescription(
                        job_id=job_id,
                        cleaned_text=response,
                    )
                )

            if descriptions:
                db.add_all(descriptions)
                await db.commit()

                logger.info(
                    "Inserted %d descriptions",
                    len(descriptions),
                )

    logger.info("Finished populating job descriptions")
