import asyncio
import json
import uuid
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.db.base import async_session
from app.core.llm import get_llm
from app.features.applications.models import Application
from app.features.jobs.models import Job, JobDescription
from app.features.jobs.services_fetcher import fetch_and_store_job_description
from app.features.workflows.critic_agent import critic_agent
from app.features.workflows.graph_state import CareerPilotState


class TargetJobExtraction(BaseModel):
    company_name: str | None = Field(
        description="The company name the user wants to apply to."
    )


async def get_target_job_id(state: CareerPilotState) -> uuid.UUID | None:
    active_app_id = state.get("active_application_id")
    if active_app_id and active_app_id != "None":
        async with async_session() as session:
            app = await session.get(
                Application,
                uuid.UUID(active_app_id)
                if isinstance(active_app_id, str)
                else active_app_id,
            )
            if app:
                return app.job_id

    messages = state.get("messages", [])
    discovered_jobs = state.get("discovered_job_ids", [])
    if not discovered_jobs:
        return None

    last_user_msg = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    if not last_user_msg:
        return uuid.UUID(discovered_jobs[0])

    try:
        llm = get_llm().with_structured_output(TargetJobExtraction)
        extraction = await llm.ainvoke(
            f"Extract the company name the user wants to apply to from this message:\n\n{last_user_msg}"
        )

        if extraction and extraction.company_name:
            async with async_session() as session:
                stmt = select(Job.id, Job.company_name).where(
                    Job.id.in_([uuid.UUID(j) for j in discovered_jobs])
                )
                res = await session.execute(stmt)
                jobs = res.all()
                for j_id, c_name in jobs:
                    if extraction.company_name.lower() in c_name.lower():
                        return j_id
    except Exception as e:
        logger.warning(f"Target job extraction failed: {e}")

    return uuid.UUID(discovered_jobs[0])


resume_prompt = ChatPromptTemplate.from_template(
    """You are an expert technical resume writer.
Your task is to generate an ATS-friendly resume tailored to a specific job posting.

## Job Details
Title: {job_title}
Company: {company_name}
Required Skills: {required_skills}

## Job Description
<job_description>
{job_description}
</job_description>

## Candidate Career Memory
<career_memory>
{career_memory}
</career_memory>

## Previous Critique
<critique>
{critique}
</critique>

## Grounding Constraints (CRITICAL)
1. **Do not hallucinate**: Do not invent any skills, certifications, work experiences, projects, or metrics not explicitly present in the <career_memory>.
2. **Missing skills**: If a required job skill is missing from the candidate's career memory, do not list it. You may emphasize related transferable skills that *are* in the career memory, but do not make up experience.
3. **Critique Adherence**: Strictly address the feedback in the <critique> section. Correct any highlighted discrepancies or weaknesses without introducing ungrounded claims.

Generate a polished markdown resume incorporating relevant skills and experiences.
"""
)

cover_letter_prompt = ChatPromptTemplate.from_template(
    """You are an expert career coach and cover letter writer.
Your task is to generate a compelling, professional cover letter tailored to a specific job posting.

## Job Details
Title: {job_title}
Company: {company_name}
Required Skills: {required_skills}

## Job Description
<job_description>
{job_description}
</job_description>

## Candidate Career Memory
<career_memory>
{career_memory}
</career_memory>

## Grounding Constraints (CRITICAL)
1. **Do not hallucinate**: Highlight only authentic experiences and achievements directly sourced from the <career_memory>. Do not invent metrics or roles.
2. **Missing skills**: Do not claim proficiency in required skills that are not present in the candidate's career memory.

Generate a professional markdown cover letter. Express enthusiasm, highlight the most relevant career memories that align with the job description, and maintain a confident, concise tone.
"""
)


async def generate_document(prompt_template, kwargs: dict) -> str:
    try:
        chain = prompt_template | get_llm()
        response = await chain.ainvoke(kwargs)
        raw_content = response.content
        if isinstance(raw_content, list):
            return "".join(
                part.get("text", "")
                for part in raw_content
                if isinstance(part, dict) and "text" in part
            )
        return str(raw_content)
    except Exception as e:
        logger.exception(f"Error generating document: {e}")
        return f"Error generating document: {e}"


async def generation_agent(
    state: CareerPilotState,
) -> Command[Literal["critic_agent"]]:
    logger.info("Generation agent starting document drafting")

    job_id = await get_target_job_id(state)
    if not job_id:
        logger.warning("No job available for generation.")
        return Command(goto="critic_agent")

    user_id = state.get("user_id", "00000000-0000-0000-0000-000000000000")
    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

    async with async_session() as session:
        memories = state.get("career_memory", {})
        job = await session.get(Job, job_id)
        if not job:
            logger.error(f"Job {job_id} not found.")
            return Command(goto="critic_agent")

        job_title = job.title
        job_company_name = job.company_name
        job_required_skills = list(job.required_skills) if job.required_skills else []

        desc_record = await session.get(JobDescription, job_id)
        fallback_job_desc = desc_record.cleaned_text if desc_record else ""

        stmt = select(Application).where(
            Application.user_id == user_uuid,
            Application.job_id == job_id,
        )
        res = await session.execute(stmt)
        existing_app = res.scalar_one_or_none()
        is_revision = existing_app is not None and existing_app.revision_count > 0

    if not is_revision:
        logger.info("Awaiting user confirmation to proceed with tailoring.")
        decision = interrupt(
            {
                "action": "generate_resume_and_cover_letter",
                "job": {
                    "id": str(job_id),
                    "title": job_title,
                    "company_name": job_company_name,
                },
            }
        )
        if isinstance(decision, str):
            try:
                decision = json.loads(decision)
            except json.JSONDecodeError:
                decision = {
                    "approved": str(decision).lower().strip()
                    in ("yes", "true", "y", "approve")
                }
        if not decision or not decision.get("approved", False):
            logger.info("User declined tailoring. Routing back to supervisor.")
            return Command(
                graph=Command.PARENT,
                goto="supervisor",
                update={"stage": "completed"},
            )

    async with async_session() as session:
        try:
            desc_record = await fetch_and_store_job_description(session, str(job_id))
            job_desc = desc_record.clean_text if desc_record else fallback_job_desc
        except Exception:
            job_desc = fallback_job_desc

        from app.core.db.models.user import User

        user_record = await session.get(User, user_uuid)
        if not user_record:
            raise ValueError(
                f"User with ID {user_uuid} does not exist in the database."
            )

        stmt = select(Application).where(
            Application.user_id == user_uuid,
            Application.job_id == job_id,
        )
        res = await session.execute(stmt)
        application = res.scalar_one_or_none()

        if application is None:
            application = Application(
                user_id=user_uuid,
                job_id=job_id,
                status="draft",
                revision_count=0,
            )
            session.add(application)
            await session.flush()

        critique = application.critique
        revision_count = application.revision_count
        app_id = application.id
        await session.commit()

    # Generate both in parallel
    kwargs = {
        "job_title": job_title,
        "company_name": job_company_name,
        "required_skills": job_required_skills,
        "job_description": job_desc or "None available.",
        "career_memory": str(memories),
        "critique": critique or "None. This is the first draft.",
    }

    resume_draft, cover_letter_draft = await asyncio.gather(
        generate_document(resume_prompt, kwargs),
        generate_document(cover_letter_prompt, kwargs),
    )

    async with async_session.begin() as session:
        app_record = await session.get(Application, app_id)
        if app_record:
            # Append revisions instead of overwriting (Issue #12)
            rev_header = f"\n\n---\n\n## Revision {revision_count + 1}\n\n"

            if app_record.resume_draft:
                app_record.resume_draft += rev_header + resume_draft
            else:
                app_record.resume_draft = resume_draft

            if getattr(app_record, "cover_letter_draft", None):
                app_record.cover_letter_draft += rev_header + cover_letter_draft
            else:
                app_record.cover_letter_draft = cover_letter_draft

            app_record.revision_count = revision_count + 1

    return Command(
        goto="critic_agent",
        update={
            "active_application_id": str(app_id),
        },
    )


subgraph_builder = StateGraph(CareerPilotState)

subgraph_builder.add_node("generation_agent", generation_agent)
subgraph_builder.add_node("critic_agent", critic_agent)

subgraph_builder.add_edge(START, "generation_agent")
subgraph_builder.add_edge("critic_agent", END)

generation_graph = subgraph_builder.compile()
