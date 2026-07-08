import uuid

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from sqlalchemy import select

from app.core.db.base import async_session
from app.core.llm import get_llm
from app.features.applications.models import Application
from app.features.jobs.models import Job
from app.features.matching.models import UserJobMatch
from app.features.workflows.graph_state import CareerPilotState

responder_prompt = ChatPromptTemplate.from_template(
    """
You are the final conversational responder for the CareerPilot multi-agent system.
Your job is to look at the current workflow state and summarize what just happened for the user.
If no subgraphs were executed and the supervisor just ended the workflow, respond conversationally to the user's latest message.

User's latest message:
{latest_message}

Recent routing history:
{routing_history}

State snapshot:
- Discovered Jobs: {discovered_jobs_count}
- Match Scores Available: {match_scores_count}
- Generated Resume Ready: {has_resume}
- Generated Cover Letter Ready: {has_cover_letter}

Generate a friendly, concise response telling the user what was accomplished.
Do not include the actual jobs, resume, or cover letter text in your response, as they will be automatically appended after your message.
"""
)


async def responder_agent(state: CareerPilotState) -> dict:
    logger.info("Responder generating final message.")

    routing_history = state.get("routing_history", [])
    discovered_job_ids = state.get("discovered_job_ids", [])
    active_application_id = state.get("active_application_id", "None")

    user_id = state.get("user_id", "00000000-0000-0000-0000-000000000000")
    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

    messages = state.get("messages", [])
    latest_message = messages[-1].content if messages else "No message provided."

    # Fetch job list from DB if any
    jobs_info = ""
    match_scores_count = 0
    job_limit = state.get("job_limit")
    if discovered_job_ids:
        job_uuids = [
            uuid.UUID(jid) if isinstance(jid, str) else jid
            for jid in discovered_job_ids
        ]
        async with async_session.begin() as session:
            stmt = (
                select(Job.title, Job.company_name, UserJobMatch.match_score)
                .outerjoin(
                    UserJobMatch,
                    (Job.id == UserJobMatch.job_id)
                    & (UserJobMatch.user_id == user_uuid),
                )
                .where(Job.id.in_(job_uuids))
                .order_by(UserJobMatch.match_score.desc().nulls_last())
            )
            if job_limit is not None:
                stmt = stmt.limit(job_limit)
            result = await session.execute(stmt)
            jobs = result.all()
            jobs_info_list = []
            for j_title, j_company, score in jobs:
                if score is not None:
                    match_scores_count += 1
                    jobs_info_list.append(
                        f"- **{j_title}** at {j_company} (Score: {score})"
                    )
                else:
                    jobs_info_list.append(f"- **{j_title}** at {j_company}")

            jobs_info = "\n".join(jobs_info_list)
            if job_limit is not None and len(discovered_job_ids) > job_limit:
                jobs_info += f"\n... and {len(discovered_job_ids) - job_limit} more."

    # Fetch resume/cover letter from DB if available
    resume_text = ""
    cover_letter_text = ""
    if active_application_id and active_application_id != "None":
        async with async_session.begin() as session:
            app_id = (
                uuid.UUID(active_application_id)
                if isinstance(active_application_id, str)
                else active_application_id
            )
            app_record = await session.get(Application, app_id)
            if app_record:
                if app_record.resume_draft:
                    resume_text = app_record.resume_draft
                if getattr(app_record, "cover_letter_draft", None):
                    cover_letter_text = app_record.cover_letter_draft

    prompt_input = {
        "latest_message": latest_message,
        "routing_history": "\n".join(routing_history[-5:])
        if routing_history
        else "No actions taken.",
        "discovered_jobs_count": len(discovered_job_ids) if discovered_job_ids else 0,
        "match_scores_count": match_scores_count,
        "has_resume": bool(resume_text),
        "has_cover_letter": bool(cover_letter_text),
    }

    llm = get_llm()
    chain = responder_prompt | llm

    try:
        response = await chain.ainvoke(prompt_input)
        final_content = response.content

        if jobs_info:
            final_content += f"\n\n### Discovered Jobs:\n{jobs_info}"

        if resume_text:
            final_content += (
                f"\n\n### Generated Resume:\n```markdown\n{resume_text}\n```"
            )

        if cover_letter_text:
            final_content += f"\n\n### Generated Cover Letter:\n```markdown\n{cover_letter_text}\n```"

        return {
            "messages": [AIMessage(content=final_content)],
            "stage": "completed",
        }
    except Exception:
        logger.exception("Responder failed.")
        return {
            "messages": [AIMessage(content="I've completed the requested actions.")],
            "stage": "completed",
        }
