import uuid

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.base import async_session
from app.db.models.agent_task import AgentTask
from app.db.models.career_memory import MemoryEntityType
from app.db.models.job import Job
from app.memory.core import get_current_memory, write_memory_facts
from app.retrieval.embeddings import get_embeddings_client
from app.retrieval.search import hybrid_search
from app.schemas.career_memory import MemoryFactWrite
from app.schemas.job import JobSearchCriteria
from app.schemas.mcp import (
    DiscoverJobsResponse,
    ErrorResponse,
    FetchJobDescriptionResponse,
    GetJobResponse,
    GetMemoryResponse,
    GetTaskStatusResponse,
    JobSearchResult,
    JobSourceData,
    JobSummaryResponse,
    ListJobsResponse,
    MemoryData,
    RunWorkflowResponse,
    SearchJobsResponse,
    StoreMemoryResponse,
)
from app.services.discovery import discover_jobs as run_discovery
from app.services.job_description_fetcher import fetch_and_store_job_description
from app.services.task_service import create_task

# MCP Server
mcp = FastMCP("CareerPilot", log_level="INFO")


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


# Tools


@mcp.tool()
async def discover_jobs(
    keywords: list[str],
    location: str = "remote",
    sources: list[str] | None = None,
    page_cap: int = 10,
) -> DiscoverJobsResponse:
    """Discover jobs matching given keywords from the job data lake."""
    async with async_session() as session:
        async with session.begin():
            criteria = JobSearchCriteria(
                keywords=keywords,
                location=location,
                sources=sources or [],
            )
            result = await run_discovery(session, criteria, page_cap=page_cap)

    return DiscoverJobsResponse(
        pages_crawled=result.pages_crawled,
        jobs_created=result.jobs_created,
        jobs_updated=result.jobs_updated,
        jobs_closed=result.jobs_closed,
        job_ids=result.job_ids,
    )


@mcp.tool()
async def list_jobs(
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ListJobsResponse:
    """List jobs from the database with optional keyword filter."""
    async with async_session() as session:
        offset = (page - 1) * page_size
        base = select(Job).where(Job.status == "active")
        count_stmt = select(func.count()).select_from(Job).where(Job.status == "active")

        if keyword:
            pattern = f"%{keyword}%"
            base = base.where(
                Job.title.ilike(pattern) | Job.company_name.ilike(pattern)
            )
            count_stmt = count_stmt.where(
                Job.title.ilike(pattern) | Job.company_name.ilike(pattern)
            )

        total = (await session.execute(count_stmt)).scalar_one() or 0
        rows = (
            (
                await session.execute(
                    base.order_by(Job.created_at.desc()).offset(offset).limit(page_size)
                )
            )
            .scalars()
            .all()
        )

    return ListJobsResponse(
        total=total,
        page=page,
        page_size=page_size,
        jobs=[_job_to_summary(j) for j in rows],
    )


@mcp.tool()
async def get_job(job_id: str) -> GetJobResponse | ErrorResponse:
    """Get full details of a specific job by ID."""
    async with async_session() as session:
        stmt = (
            select(Job)
            .options(selectinload(Job.description), selectinload(Job.sources))
            .where(Job.id == job_id)
        )
        job = (await session.execute(stmt)).scalar_one_or_none()

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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
async def store_memory(
    user_id: str,
    entity_type: str,
    fact_key: str,
    content: str,
) -> StoreMemoryResponse | ErrorResponse:
    """Store a career memory fact."""
    fact = MemoryFactWrite(
        entity_type=MemoryEntityType(entity_type),
        fact_key=fact_key,
        content={"text": content},
    )
    async with async_session() as session:
        async with session.begin():
            rows = await write_memory_facts(
                session, user_id=uuid.UUID(user_id), facts=[fact], commit=False
            )

    if not rows:
        return ErrorResponse(error="Failed to store memory")

    return StoreMemoryResponse(
        id=str(rows[0].id),
        entity_type=rows[0].entity_type,
        fact_key=rows[0].fact_key,
        content=rows[0].content,
    )


@mcp.tool()
async def get_memory(
    user_id: str,
    entity_type: str | None = None,
    fact_key: str | None = None,
) -> GetMemoryResponse:
    """Read career memory facts for a user."""
    async with async_session() as session:
        rows = await get_current_memory(session, user_id=uuid.UUID(user_id))

    if entity_type:
        rows = [r for r in rows if r.entity_type == entity_type]
    if fact_key:
        rows = [r for r in rows if r.fact_key == fact_key]

    return GetMemoryResponse(
        user_id=user_id,
        memories=[
            MemoryData(
                id=str(r.id),
                entity_type=r.entity_type,
                fact_key=r.fact_key,
                content=r.content,
                valid_from=str(r.valid_from) if r.valid_from else None,
            )
            for r in rows
        ],
    )


@mcp.tool()
async def run_workflow(
    user_id: str,
    query: str,
    job_sources: list[str] | None = None,
) -> RunWorkflowResponse:
    """Kick off a CareerPilot agent workflow via a background task."""
    async with async_session() as session:
        async with session.begin():
            task = await create_task(
                session,
                user_id=uuid.UUID(user_id),
                graph_name="main_graph",
                payload={
                    "messages": [{"role": "user", "content": query}],
                    "job_sources": job_sources or ["job_data_lake"],
                },
            )
    return RunWorkflowResponse(task_id=str(task.id), thread_id=task.thread_id)


@mcp.tool()
async def get_task_status(task_id: str) -> GetTaskStatusResponse | ErrorResponse:
    """Check the status and result of an agent task."""
    async with async_session() as session:
        task = await session.get(AgentTask, uuid.UUID(task_id))
        if task is None:
            return ErrorResponse(error="Task not found")
        return GetTaskStatusResponse(
            id=str(task.id),
            status=task.status,
            graph_name=task.graph_name,
            error=task.error,
            completed_at=str(task.completed_at) if task.completed_at else None,
            result=task.result,
        )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
