import asyncio
from typing import Any, Literal, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send
from loguru import logger
from sqlalchemy import inspect as sa_inspect
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.db.base import async_session
from app.core.llm import get_llm
from app.core.llm.embeddings import get_embeddings_client
from app.features.jobs.models import Job
from app.features.jobs.retrieval import hybrid_search
from app.features.jobs.schemas import JobCreate, JobSearchCriteria, JobSourceCreate
from app.features.jobs.services_discovery import run_discovery
from app.features.workflows.graph_state import CareerPilotState


class DiscoveryWorkerInput(TypedDict):
    source: str
    criteria_dict: dict[str, Any]


DEFAULT_CRITERIA = {
    "skills": ["python", "machine learning", "ai"],
    "location": "Remote",
    "remote_type": "remote",
    "job_function": "engineering",
    "seniority": ["senior"],
}


async def get_criteria_from_messages(messages: list[BaseMessage]) -> dict[str, Any]:
    if not messages:
        return DEFAULT_CRITERIA

    last_user_msg = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        None,
    )
    if not last_user_msg:
        return DEFAULT_CRITERIA

    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(JobSearchCriteria)
        criteria = await structured_llm.ainvoke(
            f"Extract job search criteria from this message. "
            f"CRITICAL RULES:\n"
            f"1. ONLY extract values that are explicitly requested by the user.\n"
            f"2. NEVER enumerate or guess possible values (like listing out 50 seniority levels).\n"
            f"3. If a field is not explicitly mentioned, leave it empty or None.\n\n"
            f"User Message: {last_user_msg}"
        )
        return criteria.model_dump()
    except Exception as e:
        logger.warning(f"Failed to extract criteria via LLM, using fallback: {e}")
        return DEFAULT_CRITERIA


async def discovery_agent(
    state: CareerPilotState,
) -> Command[Literal["discovery_worker"]]:
    logger.info("Discovery agent starting dispatch")
    messages = state.get("messages") or []
    sources = state.get("job_sources", ["job_data_lake"])
    criteria_dict = await get_criteria_from_messages(messages)
    limit = criteria_dict.get("limit")

    # Search local DB via hybrid_search (RRF) first
    last_user_msg = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        None,
    )
    if last_user_msg:
        try:
            logger.info("Searching local DB for jobs before calling API...")
            async with async_session() as session:
                embeddings = get_embeddings_client()
                query_embedding = await embeddings.aembed_query(last_user_msg)
                candidates = await hybrid_search(
                    session, query_embedding, last_user_msg, k=10
                )

            # Bypass API Call if at least 1 job matches and is relevant
            def is_relevant(job: Job, q: str) -> bool:
                q_words = set(q.lower().replace("/", " ").replace("-", " ").split())
                q_words -= {
                    "find",
                    "me",
                    "jobs",
                    "for",
                    "remote",
                    "senior",
                    "role",
                    "roles",
                    "position",
                    "positions",
                    "get",
                    "limit",
                }
                if not q_words:
                    return True
                title_words = set(
                    job.title.lower().replace("/", " ").replace("-", " ").split()
                )
                skills_words = {s.lower() for s in job.required_skills}
                return bool(q_words & title_words or q_words & skills_words)

            good_candidates = [
                c
                for c in candidates
                if c.score >= 0.005 and is_relevant(c.job, last_user_msg)
            ]
            if len(good_candidates) >= 1:
                logger.info(
                    f"Found {len(good_candidates)} matching jobs locally in DB. Bypassing API discovery."
                )
                slice_limit = limit if limit is not None else len(good_candidates)
                return Command(
                    goto=END,
                    update={
                        "discovered_job_ids": ["__CLEAR__"]
                        + [str(c.job.id) for c in good_candidates[:slice_limit]],
                        "stage": "memory",
                        "job_limit": limit,
                    },
                )
            logger.info(
                "Insufficient matches in local DB. Proceeding to external API discovery."
            )
        except Exception as e:
            logger.warning(
                f"Local DB pre-search failed: {e}. Proceeding to API discovery."
            )

    sends = [
        Send(
            "discovery_worker",
            DiscoveryWorkerInput(source=source, criteria_dict=criteria_dict),
        )
        for source in sources
    ]
    logger.info(f"Fanning out to {len(sends)} discovery workers")
    return Command(
        goto=sends,
        update={
            "discovered_job_ids": ["__CLEAR__"],
            "stage": "memory",
            "job_limit": limit,
        },
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def discover_jobs_with_retry(session, criteria, source_name):
    # Retry wrapper
    return await run_discovery(db=session, criteria=criteria, source_name=source_name)


def build_job_create(job: Job, fallback_source: str) -> JobCreate:
    source_info = job.sources[0] if job.sources else None
    source_create = (
        JobSourceCreate(
            source_name=source_info.source_name,
            source_job_id=source_info.source_job_id,
            source_url=source_info.source_url,
            first_seen_at=source_info.first_seen_at,
        )
        if source_info
        else JobSourceCreate(
            source_name=fallback_source,
            source_job_id="unknown",
            source_url="http://unknown.com",
            first_seen_at=job.created_at,
        )
    )

    column_values = {
        col.key: getattr(job, col.key) for col in sa_inspect(job).mapper.column_attrs
    }
    return JobCreate(**column_values, source=source_create)


# Cap concurrency during parallel fanned-out runs to prevent connection pool exhaustion (Issue #4 in audit)
concurrency_semaphore = asyncio.Semaphore(5)


async def discovery_worker(state: DiscoveryWorkerInput) -> dict[str, Any]:
    source = state["source"]
    criteria_dict = state["criteria_dict"]

    logger.info(
        f"Discovery worker executing for source: {source} with criteria: {criteria_dict}"
    )

    if source != "job_data_lake":
        logger.warning(f"Source '{source}' is not supported yet. Returning empty.")
        return {"discovered_job_ids": []}

    criteria = JobSearchCriteria(**criteria_dict)
    async with concurrency_semaphore:
        async with async_session() as session:
            try:
                result = await discover_jobs_with_retry(session, criteria, source)
            except Exception:
                logger.exception(f"Discovery failed for source {source} after retries")
                return {"discovered_job_ids": []}

        uuid_ids = []
        if result.job_ids:
            limit = criteria.limit
            slice_limit = limit if limit is not None else len(result.job_ids)
            uuid_ids = [str(jid) for jid in result.job_ids[:slice_limit]]

        logger.info(f"Discovery worker for {source} found {len(uuid_ids)} jobs.")
        return {"discovered_job_ids": uuid_ids}


subgraph_builder = StateGraph(CareerPilotState)
subgraph_builder.add_node("discovery_agent", discovery_agent)
subgraph_builder.add_node("discovery_worker", discovery_worker)

subgraph_builder.add_edge(START, "discovery_agent")

discovery_graph = subgraph_builder.compile()
