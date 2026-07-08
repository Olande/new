import uuid
from typing import Any, Literal

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from loguru import logger
from sqlalchemy import select

from app.core.db.base import async_session
from app.features.jobs.company_research import company_research_agent
from app.features.jobs.models import Job
from app.features.memory.services import get_current_memory
from app.features.workflows.graph_state import CareerPilotState

load_dotenv()


# Check the overlap between job and user skills using Jaccard score
def score_job(job_skills: set[str], user_skills: set[str]) -> float:
    union = job_skills | user_skills

    if not union:
        return 1.0

    return round(len(job_skills & user_skills) / len(union), 2)


async def matching_agent(state: CareerPilotState) -> dict[str, Any]:
    logger.info("Matching agent starting match score computation")
    discovered_job_ids = state.get("discovered_job_ids") or []
    user_id = state.get("user_id", "00000000-0000-0000-0000-000000000000")
    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    job_uuids = [
        uuid.UUID(jid) if isinstance(jid, str) else jid for jid in discovered_job_ids
    ]

    async with async_session() as session:
        # Load user skills directly from the DB
        memories = await get_current_memory(session, user_id=user_uuid)
        user_skills = {
            mem.fact_key.lower()
            for mem in memories
            if (
                mem.entity_type.value
                if hasattr(mem.entity_type, "value")
                else str(mem.entity_type)
            )
            == "skill"
        }

        # Load jobs from the DB
        if not job_uuids:
            logger.info("No discovered job IDs to match.")
            return {"match_scores": []}

        stmt = select(Job).where(Job.id.in_(job_uuids))
        res = await session.execute(stmt)
        jobs = res.scalars().all()

    candidates = [
        {
            "job_id": str(job.id),
            "score": score_job({s.lower() for s in job.required_skills}, user_skills),
        }
        for job in jobs
    ]
    job_order = {str(jid): i for i, jid in enumerate(discovered_job_ids)}
    candidates.sort(
        key=lambda c: (c["score"], -job_order.get(c["job_id"], 0)), reverse=True
    )

    logger.info(f"Job matching completed for {len(candidates)} candidates.")
    return {"match_scores": candidates}


def matching_start(
    state: CareerPilotState,
) -> Command[Literal["matching_agent", "company_research"]]:
    logger.info(
        "Matching subgraph dispatcher: fanning out to matching_agent and company_research"
    )
    return Command(goto=["matching_agent", "company_research"])


def matching_join(state: CareerPilotState) -> Command:
    logger.info("Matching subgraph joined: returning control to parent supervisor")
    # return Command(graph=Command.PARENT, goto="supervisor", update={"stage": "generation"})
    return {"stage": "generation"}


subgraph_builder = StateGraph(CareerPilotState)
subgraph_builder.add_node("matching_start", matching_start)
subgraph_builder.add_node("matching_agent", matching_agent)
subgraph_builder.add_node("company_research", company_research_agent)
subgraph_builder.add_node("matching_join", matching_join)

subgraph_builder.add_edge(START, "matching_start")
subgraph_builder.add_edge("matching_agent", "matching_join")
subgraph_builder.add_edge("company_research", "matching_join")
subgraph_builder.add_edge("matching_join", END)

matching_graph = subgraph_builder.compile()
