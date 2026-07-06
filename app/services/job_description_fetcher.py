from datetime import datetime, timezone

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.db.models.job_description import JobDescription
from app.db.models.job_source import JobSource
from app.config.settings import settings

JINA_READER_BASE = "https://r.jina.ai/"
FETCH_TIMEOUT_S = 20.0


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_via_jina_reader(url: str) -> str:
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S) as client:
        resp = await client.get(
            f"{JINA_READER_BASE}{url}",
            headers={"Authorization": f"Bearer {settings.jina_api_key}"},
        )
        resp.raise_for_status()
        return resp.text


async def fetch_and_store_job_description(
    session: AsyncSession,
    job_id: str,
) -> JobDescription | None:

    source = (
        await session.execute(
            select(JobSource)
            .where(JobSource.job_id == job_id)
            .order_by(JobSource.last_checked_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if source is None or not source.source_url:
        logger.warning(
            f"No source url found for job_id={job_id}, skipping description fetch"
        )
        return None

    url = source.source_url

    try:
        cleaned_text = await fetch_via_jina_reader(url)
    except Exception as exc:
        logger.warning(f"Failed to fetch description for job_id={job_id}: {exc}")
        return None

    if not cleaned_text.strip():
        logger.info(f"No extractable text for job_id={job_id}")
        return None

    stmt = (
        pg_insert(JobDescription)
        .values(
            job_id=job_id,
            cleaned_text=cleaned_text,
            fetched_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["job_id"])
    )
    await session.execute(stmt)
    await session.commit()

    jd = await session.get(JobDescription, job_id)
    return jd
