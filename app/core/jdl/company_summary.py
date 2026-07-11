import logging

from langchain_tavily import TavilySearch
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from app.core.retry import default_retry

from app.core.batch import process_in_batches
from app.core.config.settings import settings
from app.core.db.base import async_session
from app.core.db.models.job import Job

logger = logging.getLogger(__name__)


def get_tavily(include_answer: bool = True, k: int = 5) -> TavilySearch:
    return TavilySearch(
        include_answer=include_answer,
        k=k,
        tavily_api_key=settings.tavily_api_key,
    )


@default_retry(initial=2, max_wait=60)
async def fetch_company_summary(
    tavily: TavilySearch,
    company_name: str,
) -> str | None:
    response = await tavily.ainvoke(
        f"Provide a concise overview of the company {company_name}."
    )
    return response.get("answer")


async def backfill_summaries_from_existing(db: AsyncSession) -> int:
    """
    Copy an existing company_summary onto any row of the same company
    that doesn't already have one.
    """
    source_job = aliased(Job)

    stmt = (
        update(Job)
        .values(
            company_summary=(
                select(source_job.company_summary)
                .where(
                    source_job.company_name == Job.company_name,
                    source_job.company_summary.is_not(None),
                )
                .limit(1)
                .scalar_subquery()
            )
        )
        .where(Job.company_summary.is_(None))
    )

    result = await db.execute(stmt)
    await db.commit()

    return result.rowcount or 0


async def populate_company_summaries(batch_size: int = 10) -> None:
    """
    Populate summaries for all companies that currently have no summary.
    """
    async with async_session() as db:
        copied = await backfill_summaries_from_existing(db)

        if copied:
            logger.info(
                "Copied existing summaries onto %d job rows (no API cost)",
                copied,
            )

        result = await db.execute(
            select(Job.company_name).where(Job.company_summary.is_(None)).distinct()
        )
        companies = result.scalars().all()

        if not companies:
            logger.info("No companies need a new summary lookup")
            return

        tavily = get_tavily()

        responses = await process_in_batches(
            items=list(companies),
            processor=lambda name: fetch_company_summary(tavily, name),
            batch_size=batch_size,
            max_concurrency=batch_size,
        )

        for company_name, response in zip(companies, responses, strict=False):
            if isinstance(response, Exception):
                logger.warning(
                    "Failed to summarize %s: %s",
                    company_name,
                    response,
                )
                continue

            if not response:
                continue

            await db.execute(
                update(Job)
                .where(Job.company_name == company_name)
                .values(company_summary=response)
            )

            logger.info("Summarized: %s", company_name)

        await db.commit()


async def populate_for_companies(
    db: AsyncSession,
    company_names: set[str],
    batch_size: int = 10,
) -> None:
    """
    Populate company_summary only for the specified companies.
    """
    if not company_names:
        return

    source_job = aliased(Job)

    backfill_stmt = (
        update(Job)
        .values(
            company_summary=(
                select(source_job.company_summary)
                .where(
                    source_job.company_name == Job.company_name,
                    source_job.company_summary.is_not(None),
                )
                .limit(1)
                .scalar_subquery()
            )
        )
        .where(
            Job.company_name.in_(company_names),
            Job.company_summary.is_(None),
        )
    )

    backfilled = (await db.execute(backfill_stmt)).rowcount or 0

    if backfilled:
        logger.info(
            "Copied existing summaries onto %d job rows (no API cost)",
            backfilled,
        )

    result = await db.execute(
        select(Job.company_name)
        .where(
            Job.company_name.in_(company_names),
            Job.company_summary.is_(None),
        )
        .distinct()
    )

    missing = result.scalars().all()

    if not missing:
        return

    tavily = get_tavily()

    responses = await process_in_batches(
        items=list(missing),
        processor=lambda name: fetch_company_summary(tavily, name),
        batch_size=batch_size,
        max_concurrency=batch_size,
    )

    for company_name, response in zip(missing, responses, strict=False):
        if isinstance(response, Exception):
            logger.warning(
                "Failed to summarize %s: %s",
                company_name,
                response,
            )
            continue

        if not response:
            continue

        await db.execute(
            update(Job)
            .where(Job.company_name == company_name)
            .values(company_summary=response)
        )

        logger.info("Summarized: %s", company_name)

    await db.commit()
