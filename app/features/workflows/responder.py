from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from sqlalchemy import select

from app.core.db.base import async_session
from app.core.llm import get_llm
from app.features.applications.models import Application
from app.features.jobs.models import Job
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

Generate a friendly, concise response telling the user what was accomplished.
Do not include the actual jobs or resume text in your response, as they will be automatically appended after your message.
"""
)


async def responder_agent(state: CareerPilotState) -> dict:
    logger.info("Responder generating final message.")

    routing_history = state.get("routing_history", [])
    discovered_job_ids = state.get("discovered_job_ids", [])
    match_scores = state.get("match_scores", [])
    active_application_id = state.get("active_application_id", "None")

    messages = state.get("messages", [])
    latest_message = messages[-1].content if messages else "No message provided."

    # Fetch job list from DB if any
    jobs_info = ""
    if discovered_job_ids:
        async with async_session.begin() as session:
            stmt = (
                select(Job.title, Job.company_name)
                .where(Job.id.in_(discovered_job_ids))
                .limit(20)
            )
            result = await session.execute(stmt)
            jobs = result.all()
            jobs_info = "\n".join(
                [f"- **{j.title}** at {j.company_name}" for j in jobs]
            )
            if len(discovered_job_ids) > 20:
                jobs_info += f"\n... and {len(discovered_job_ids) - 20} more."

    # Fetch resume from DB if available
    resume_text = ""
    if active_application_id and active_application_id != "None":
        async with async_session.begin() as session:
            app_record = await session.get(Application, active_application_id)
            if app_record and app_record.resume_draft:
                resume_text = app_record.resume_draft

    prompt_input = {
        "latest_message": latest_message,
        "routing_history": "\n".join(routing_history[-5:])
        if routing_history
        else "No actions taken.",
        "discovered_jobs_count": len(discovered_job_ids) if discovered_job_ids else 0,
        "match_scores_count": len(match_scores) if match_scores else 0,
        "has_resume": bool(resume_text),
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

        return {"messages": [AIMessage(content=final_content)]}
    except Exception:
        logger.exception("Responder failed.")
        return {
            "messages": [AIMessage(content="I've completed the requested actions.")]
        }
