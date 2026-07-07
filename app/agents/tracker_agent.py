import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from loguru import logger

from app.db.base import async_session
from app.db.models.application import Application
from app.db.models.job import Job
from app.schemas.graph_state import CareerPilotState


async def update_application_status(
    *,
    application_id: uuid.UUID,
    status: str,
    notes: str,
) -> None:
    """Update application record status."""
    async with async_session.begin() as session:
        application = await session.get(Application, application_id)
        if application:
            application.status = status
            application.notes = notes


async def tracker_agent(
    state: CareerPilotState,
) -> Command[Any]:
    logger.info("Tracker agent awaiting user approval.")

    match_scores = state.get("match_scores", [])
    best_candidate = match_scores[0] if match_scores else None
    active_application_id = state.get("active_application_id")

    if best_candidate is None or not active_application_id:
        logger.warning("No candidate or active application ID available for tracking.")

        return Command(
            graph=Command.PARENT,
            goto="supervisor",
            update={
                "application_status": {
                    "status": "no_candidate",
                },
                "stage": "completed",
            },
        )

    job_id = best_candidate["job_id"]
    job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
    app_uuid = (
        uuid.UUID(active_application_id)
        if isinstance(active_application_id, str)
        else active_application_id
    )

    async with async_session() as session:
        job = await session.get(Job, job_uuid)
        if not job:
            logger.error(f"Job {job_id} not found in DB.")
            return Command(
                graph=Command.PARENT,
                goto="supervisor",
                update={"application_status": {"status": "error"}},
            )
        job_title = job.title
        company_name = job.company_name

        application = await session.get(Application, app_uuid)
        if not application:
            logger.error(f"Application {active_application_id} not found in DB.")
            return Command(
                graph=Command.PARENT,
                goto="supervisor",
                update={"application_status": {"status": "error"}},
            )
        resume_draft = application.resume_draft or ""

    decision = interrupt(
        {
            "action": "submit_application",
            "application_id": str(active_application_id),
            "job": {
                "id": str(job_id),
                "title": job_title,
                "company_name": company_name,
            },
            "resume_preview": resume_draft,
        }
    )

    approved = decision.get("approved", False)

    logger.info(
        "User {} application for '{}' at '{}'.",
        "approved" if approved else "rejected",
        job_title,
        company_name,
    )

    if approved:
        status = "submitted"
        notes = "Application submitted after user approval."
    else:
        status = "cancelled"
        notes = "Application cancelled during human review."

    await update_application_status(
        application_id=app_uuid,
        status=status,
        notes=notes,
    )

    logger.info(
        "Application status '{}' recorded for job '{}'.",
        status,
        job_title,
    )

    return Command(
        graph=Command.PARENT,
        goto="supervisor",
        update={
            "application_status": {
                "status": status,
                "job_id": str(job_id),
            },
            "stage": "completed",
        },
    )


subgraph_builder = StateGraph(CareerPilotState)

subgraph_builder.add_node("tracker_agent", tracker_agent)

subgraph_builder.add_edge(START, "tracker_agent")
subgraph_builder.add_edge("tracker_agent", END)

tracker_graph = subgraph_builder.compile()
