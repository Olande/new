import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config.settings import settings
from app.features.jobs.models import JobDescription
from app.features.jobs.repository import get_job_source, upsert_job_description

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
    source = await get_job_source(session, job_id)

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

    return await upsert_job_description(session, job_id, cleaned_text)
