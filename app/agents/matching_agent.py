import uuid
from typing import Any, Literal

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from loguru import logger

from app.agents.company_research import company_research_agent
from app.schemas.graph_state import CareerPilotState

from sqlalchemy import select
from app.db.base import async_session
from app.db.models.job import Job
from app.memory.core import get_current_memory

_ = load_dotenv()


def _score_job(job_skills: set[str], user_skills: set[str]) -> float:
    if not job_skills or not user_skills:
        return 0.80
    overlap = job_skills & user_skills
    return round(min(max(0.5 + (len(overlap) / len(job_skills)) * 0.5, 0.0), 1.0), 2)


async def matching_agent(state: CareerPilotState) -> dict[str, Any]:
    logger.info("Matching agent starting match score computation")
    discovered_job_ids = state.get("discovered_job_ids") or []
    user_id = state["user_id"]
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
            "score": _score_job({s.lower() for s in job.required_skills}, user_skills),
        }
        for job in jobs
    ]
    candidates.sort(key=lambda c: c["score"], reverse=True)

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
