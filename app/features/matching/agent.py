import uuid
from typing import Any

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.db.base import async_session
from app.features.jobs.models import Job
from app.features.matching.models import UserJobMatch
from app.features.memory.services import get_current_memory
from app.features.workflows.graph_state import CareerPilotState

load_dotenv()


# Check the overlap between job and user skills using token-based containment similarity
def score_job(job_skills: set[str], user_skills: set[str]) -> float:
    def tokenize(skills):
        tokens = set()
        for s in skills:
            s_clean = (
                s.replace("(", " ")
                .replace(")", " ")
                .replace("/", " ")
                .replace("-", " ")
                .replace(",", " ")
                .lower()
            )
            tokens.update([w for w in s_clean.split() if len(w) > 1])
        return tokens

    job_tokens = tokenize(job_skills)
    user_tokens = tokenize(user_skills)

    if not job_tokens:
        return 0.0

    return round(len(job_tokens & user_tokens) / len(job_tokens), 2)


async def matching_agent(state: CareerPilotState) -> dict[str, Any]:
    logger.info("Matching agent computing scores and saving to DB")
    discovered_job_ids = state.get("discovered_job_ids") or []
    user_id = state.get("user_id", "00000000-0000-0000-0000-000000000000")
    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    job_uuids = [
        uuid.UUID(jid) if isinstance(jid, str) else jid for jid in discovered_job_ids
    ]

    if not job_uuids:
        logger.info("No discovered job IDs to match.")
        return {"stage": "generation"}

    async with async_session.begin() as session:
        # Load user skills directly from the DB
        memories = await get_current_memory(session, user_id=user_uuid)

        user_skills = set()
        generic_keys = {
            "programming language",
            "programming_language",
            "technical skills",
            "technical_skills",
            "field of expertise",
            "field of study",
            "target_role_expertise",
            "domain_expertise",
            "skills",
        }
        for mem in memories:
            entity_type = (
                mem.entity_type.value
                if hasattr(mem.entity_type, "value")
                else str(mem.entity_type)
            )
            if entity_type in ("skill", "employment_history"):
                fact_key_lower = mem.fact_key.lower()
                if fact_key_lower not in generic_keys:
                    user_skills.add(fact_key_lower)

                if isinstance(mem.content, dict):
                    text_val = mem.content.get("text")
                    if isinstance(text_val, str) and text_val:
                        user_skills.add(text_val.lower())

        # Load jobs from the DB
        stmt = select(Job).where(Job.id.in_(job_uuids))
        res = await session.execute(stmt)
        jobs = res.scalars().all()

        candidates = [
            {
                "user_id": user_uuid,
                "job_id": job.id,
                "match_score": score_job(
                    {s.lower() for s in job.required_skills}, user_skills
                ),
            }
            for job in jobs
        ]

        if candidates:
            insert_stmt = insert(UserJobMatch).values(candidates)
            insert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["user_id", "job_id"],
                set_={"match_score": insert_stmt.excluded.match_score},
            )
            await session.execute(insert_stmt)
            logger.info(f"Saved match scores for {len(candidates)} jobs.")

    return {"stage": "generation"}


subgraph_builder = StateGraph(CareerPilotState)
subgraph_builder.add_node("matching_agent", matching_agent)

subgraph_builder.add_edge(START, "matching_agent")
subgraph_builder.add_edge("matching_agent", END)

matching_graph = subgraph_builder.compile()
