import asyncio
import logging
from typing import Any

from langchain_tavily import TavilySearch
from sqlalchemy import select

from app.core.llm import get_llm
from app.db.base import async_session
from app.db.models.job import Job

logger = logging.getLogger(__name__)


def get_tavily(search_depth: str = "advanced", k: int = 5, include_answer: bool = True):
    return TavilySearch(
        max_results=k, search_depth=search_depth, include_answer=include_answer
    )


async def _research_one_company(company: str) -> tuple[str, str]:
    logger.info(f"Researching company: {company}")
    tavily_search = get_tavily()
    llm = get_llm()

    query = f"What is {company} company? Focus on products, culture, size, and domain."
    res = await tavily_search.ainvoke(query)
    search_result = (
        res.get("answer") if isinstance(res, dict) else getattr(res, "answer", str(res))
    )

    prompt = (
        f"Summarize the following research data about {company} into a clean summary "
        f"detailing domain, key products, culture, and size:\n{search_result}"
    )
    summary = await llm.ainvoke(prompt)
    content = summary.content
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    elif not isinstance(content, str):
        content = str(content)

    return company, content


async def company_research_agent(state: dict) -> dict[str, Any]:
    logger.info("Company research agent starting")
    discovered_job_ids = state.get("discovered_job_ids") or []

    if not discovered_job_ids:
        logger.info("No jobs to research.")
        return {}

    import uuid

    job_uuids = [
        uuid.UUID(jid) if isinstance(jid, str) else jid for jid in discovered_job_ids
    ]

    async with async_session() as session:
        stmt = select(Job).where(Job.id.in_(job_uuids))
        res = await session.execute(stmt)
        jobs = res.scalars().all()

    companies = list({job.company_name for job in jobs if job.company_name})

    results = await asyncio.gather(
        *(_research_one_company(c) for c in companies),
        return_exceptions=True,
    )

    async with async_session.begin() as session:
        for res in results:
            if isinstance(res, Exception):
                logger.warning(f"Company research failed: {res}")
                continue
            company, summary = res

            stmt = select(Job).where(Job.company_name == company)
            db_jobs = (await session.execute(stmt)).scalars().all()
            for j in db_jobs:
                j.company_summary = summary

    return {}
