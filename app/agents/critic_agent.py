from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import Command
from loguru import logger

from app.core.llm import get_llm
from app.db.base import async_session
from app.db.models.application import Application
from app.db.models.job import Job
from app.schemas.graph_state import CareerPilotState
from app.schemas.agents.critic_agent import ResumeEvaluator


prompt = """
Evaluate this draft resume against the target job "{job_title}" at "{company_name}"
and the user's career memory.

Resume Draft:
{resume_draft}

User Career Memory:
{career_memory}

Provide a short critique and a fitness score between 0.0 and 1.0.

"""


async def evaluate_resume(
    resume_draft: str, career_memory: list, job_title: str, company_name: str
):
    prompt_template = ChatPromptTemplate.from_template(prompt)
    structured_llm = get_llm().with_structured_output(ResumeEvaluator)
    chain = prompt_template | structured_llm
    res = await chain.ainvoke(
        {
            "resume_draft": resume_draft,
            "career_memory": str(career_memory),
            "job_title": job_title,
            "company_name": company_name,
        }
    )
    return res.resume_critique, res.resume_score


async def critic_agent(state: CareerPilotState) -> Command[Literal["resume_agent"]]:
    logger.info("Critic agent starting resume evaluation")
    match_scores = state.get("match_scores", [])
    best_candidate = match_scores[0] if match_scores else None
    active_application_id = state.get("active_application_id")

    if not active_application_id or not best_candidate:
        logger.warning("Missing active_application_id or best_candidate in state")
        return Command(
            graph=Command.PARENT, goto="supervisor", update={"stage": "tracker"}
        )

    import uuid

    app_uuid = (
        uuid.UUID(active_application_id)
        if isinstance(active_application_id, str)
        else active_application_id
    )

    async with async_session() as session:
        # Load memories from DB
        memories = state.get("career_memory", {})

        job_id = best_candidate["job_id"]
        job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
        job = await session.get(Job, job_uuid)
        if not job:
            logger.error(f"Job {job_id} not found")
            return Command(
                graph=Command.PARENT, goto="supervisor", update={"stage": "tracker"}
            )

        # Load application record
        app_record = await session.get(Application, app_uuid)
        if not app_record:
            logger.error(f"Application record {active_application_id} not found")
            return Command(
                graph=Command.PARENT, goto="supervisor", update={"stage": "tracker"}
            )
        resume_draft = app_record.resume_draft or ""
        revision_count = app_record.revision_count or 0

    critique, score = await evaluate_resume(
        resume_draft, memories, job.title, job.company_name
    )
    logger.info(f"Resume critique score: {score:.2f}, revision count: {revision_count}")

    async with async_session.begin() as session:
        # Fetch again to update in transaction
        db_app = await session.get(Application, app_uuid)
        if db_app:
            db_app.critique = critique
            db_app.fitness_score = score

    if score >= 0.85 or revision_count >= 3:
        logger.info(
            "Resume criteria met or revision limit reached. Routing to supervisor (tracker stage)."
        )
        return Command(
            graph=Command.PARENT,
            goto="supervisor",
            update={
                "stage": "tracker",
                "active_application_id": str(app_uuid),
            },
        )
    logger.info(
        "Resume score below threshold. Routing back to resume_agent for revision."
    )
    return Command(goto="resume_agent")
