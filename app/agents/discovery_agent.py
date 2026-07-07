from typing import Any, Literal, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send
from loguru import logger
from sqlalchemy import inspect as sa_inspect
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.normalization_agent import normalization_agent
from app.core.llm import get_llm
from app.db.base import async_session
from app.db.models.job import Job
from app.retrieval.embeddings import get_embeddings_client
from app.retrieval.search import hybrid_search
from app.schemas.graph_state import CareerPilotState
from app.schemas.job import JobCreate, JobSearchCriteria, JobSourceCreate
from app.services.discovery import discover_jobs


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
            f"Return structured search criteria: {last_user_msg}"
        )
        return criteria.model_dump()
    except Exception as e:
        logger.warning(f"Failed to extract criteria via LLM, using fallback: {e}")
        return DEFAULT_CRITERIA


async def discovery_agent(
    state: CareerPilotState,
) -> Command[Literal["discovery_worker", "normalization_agent"]]:
    logger.info("Discovery agent starting dispatch")
    messages = state.get("messages") or []
    sources = state.get("job_sources", ["job_data_lake"])
    criteria_dict = await get_criteria_from_messages(messages)

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

            # Bypass API Call if at least 3 jobs match
            good_candidates = [c for c in candidates if c.score >= 0.012]
            if len(good_candidates) >= 3:
                logger.info(
                    f"Found {len(good_candidates)} matching jobs locally in DB. Bypassing API discovery."
                )
                return Command(
                    goto="normalization_agent",
                    update={
                        "discovered_job_ids": [str(c.job.id) for c in good_candidates]
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
    return Command(goto=sends)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def discover_jobs_with_retry(session, criteria, source_name):
    return await discover_jobs(db=session, criteria=criteria, source_name=source_name)


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
    async with async_session() as session:
        try:
            result = await discover_jobs_with_retry(session, criteria, source)
        except Exception:
            logger.exception(f"Discovery failed for source {source} after retries")
            return {"discovered_job_ids": []}

        uuid_ids = []
        if result.job_ids:
            uuid_ids = [str(jid) for jid in result.job_ids]

        logger.info(f"Discovery worker for {source} found {len(uuid_ids)} jobs.")
        return {"discovered_job_ids": uuid_ids}


subgraph_builder = StateGraph(CareerPilotState)
subgraph_builder.add_node("discovery_agent", discovery_agent)
subgraph_builder.add_node("discovery_worker", discovery_worker)
subgraph_builder.add_node("normalization_agent", normalization_agent)

subgraph_builder.add_edge(START, "discovery_agent")
subgraph_builder.add_edge("discovery_worker", "normalization_agent")
subgraph_builder.add_edge("normalization_agent", END)

discovery_graph = subgraph_builder.compile()
