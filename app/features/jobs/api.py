from mcp.server.fastmcp import FastMCP

from app.api.schemas import (
    DiscoverJobsResponse,
    ErrorResponse,
    FetchJobDescriptionResponse,
    GetJobResponse,
    JobSearchResult,
    JobSourceData,
    JobSummaryResponse,
    ListJobsResponse,
    SearchJobsResponse,
)
from app.core.db.base import async_session
from app.core.llm.embeddings import get_embeddings_client
from app.features.jobs.models import Job
from app.features.jobs.repository import get_job_repo, list_jobs_repo
from app.features.jobs.retrieval import hybrid_search
from app.features.jobs.schemas import JobSearchCriteria
from app.features.jobs.services_discovery import run_discovery
from app.features.jobs.services_fetcher import fetch_and_store_job_description


def _job_to_summary(job: Job) -> JobSummaryResponse:
    return JobSummaryResponse(
        id=str(job.id),
        title=job.title,
        company=job.company_name,
        locations=job.locations,
        role=job.role,
        seniority=job.seniority,
        employment_type=job.employment_type,
        remote_type=job.remote_type,
        posted_at=str(job.posted_at) if job.posted_at else None,
    )


async def discover_jobs(
    keywords: list[str],
    location: str = "remote",
    sources: list[str] | None = None,
    page_cap: int = 10,
) -> DiscoverJobsResponse:
    """Discover jobs matching given keywords from the job data lake."""
    async with async_session() as session:
        criteria = JobSearchCriteria(
            keywords=keywords,
            location=location,
            sources=sources or [],
        )
        result = await run_discovery(
            session, criteria, source_name="job_data_lake", page_cap=page_cap
        )

    return DiscoverJobsResponse(
        pages_crawled=result.pages_crawled,
        jobs_created=result.jobs_created,
        jobs_updated=result.jobs_updated,
        jobs_closed=result.jobs_closed,
        job_ids=result.job_ids,
    )


async def list_jobs(
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ListJobsResponse:
    """List jobs from the database with optional keyword filter."""
    async with async_session() as session:
        total, rows = await list_jobs_repo(session, keyword, page, page_size)

    return ListJobsResponse(
        total=total,
        page=page,
        page_size=page_size,
        jobs=[_job_to_summary(j) for j in rows],
    )


async def get_job(job_id: str) -> GetJobResponse | ErrorResponse:
    """Get full details of a specific job by ID."""
    async with async_session() as session:
        job = await get_job_repo(session, job_id)

        if job is None:
            return ErrorResponse(error="Job not found")

        desc = None
        if job.description:
            desc = (job.description.cleaned_text or "")[:5000]

        sources_data = [
            JobSourceData(
                name=s.source_name,
                url=s.source_url,
                source_job_id=s.source_job_id,
            )
            for s in (job.sources or [])
        ]

    return GetJobResponse(
        id=str(job.id),
        title=job.title,
        company=job.company_name,
        domain=job.domain_name,
        role=job.role,
        job_function=job.job_function,
        seniority=job.seniority,
        employment_type=job.employment_type,
        remote_type=job.remote_type,
        locations=job.locations,
        countries=job.countries,
        required_skills=job.required_skills,
        employee_count=job.employee_count,
        funding=job.funding,
        description_preview=desc,
        posted_at=str(job.posted_at) if job.posted_at else None,
        status=job.status,
        sources=sources_data,
    )


async def search_jobs(query: str, k: int = 10) -> SearchJobsResponse:
    """Semantic + lexical hybrid search across active jobs."""
    async with async_session() as session:
        embeddings = get_embeddings_client()
        query_embedding = await embeddings.aembed_query(query)
        candidates = await hybrid_search(
            session, query_embedding=query_embedding, query_text=query, k=k
        )

    return SearchJobsResponse(
        query=query,
        results=[
            JobSearchResult(
                id=str(c.job.id),
                title=c.job.title,
                company=c.job.company_name,
                role=c.job.role,
                locations=c.job.locations,
                remote_type=c.job.remote_type,
                score=c.score,
                skills=c.job.required_skills,
            )
            for c in candidates
        ],
    )


async def fetch_job_description(
    job_id: str,
) -> FetchJobDescriptionResponse | ErrorResponse:
    """Fetch and store a job description via Jina Reader."""
    async with async_session() as session:
        jd = await fetch_and_store_job_description(session, job_id)

    if jd is None:
        return ErrorResponse(error="Failed to fetch job description")

    return FetchJobDescriptionResponse(
        job_id=str(jd.job_id),
        cleaned_text=jd.cleaned_text[:5000] if jd.cleaned_text else None,
        fetched_at=str(jd.fetched_at) if jd.fetched_at else None,
    )


def register_job_endpoints(mcp: FastMCP) -> None:
    mcp.tool()(discover_jobs)
    mcp.tool()(list_jobs)
    mcp.tool()(get_job)
    mcp.tool()(search_jobs)
    mcp.tool()(fetch_job_description)
