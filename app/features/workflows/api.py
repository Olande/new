import uuid

from mcp.server.fastmcp import FastMCP

from app.api.schemas import ErrorResponse, GetTaskStatusResponse, RunWorkflowResponse
from app.core.db.base import async_session
from app.features.workflows.repository import get_task_repo, resume_task_repo
from app.features.workflows.services import create_task


class ResumeWorkflowResponse(RunWorkflowResponse):
    status: str


async def run_workflow(
    user_id: str,
    query: str,
    job_sources: list[str] | None = None,
) -> RunWorkflowResponse:
    """Kick off a CareerPilot agent workflow via a background task."""
    async with async_session() as session, session.begin():
        task = await create_task(
            session,
            user_id=uuid.UUID(user_id),
            graph_name="main_graph",
            payload={
                "messages": [{"role": "user", "content": query}],
                "job_sources": job_sources or ["job_data_lake"],
            },
        )
    return RunWorkflowResponse(task_id=str(task.id), thread_id=task.thread_id)


async def get_task_status(task_id: str) -> GetTaskStatusResponse | ErrorResponse:
    """Check the status and result of an agent task."""
    async with async_session() as session:
        task = await get_task_repo(session, uuid.UUID(task_id))
        if task is None:
            return ErrorResponse(error="Task not found")
        return GetTaskStatusResponse(
            id=str(task.id),
            status=task.status,
            graph_name=task.graph_name,
            error=task.error,
            completed_at=str(task.completed_at) if task.completed_at else None,
            result=task.result,
        )


async def resume_workflow(
    task_id: str,
    resume_data: dict,
) -> ResumeWorkflowResponse | ErrorResponse:
    """Resume a paused workflow by providing the required human-in-the-loop data."""
    try:
        task_uuid = uuid.UUID(task_id)
        async with async_session.begin() as session:
            await resume_task_repo(session, task_uuid, resume_data)
        return ResumeWorkflowResponse(task_id=task_id, thread_id="", status="pending")
    except Exception as e:
        import traceback

        return ErrorResponse(
            error=f"Failed to resume workflow: {e}\n{traceback.format_exc()}"
        )


def register_workflow_endpoints(mcp: FastMCP) -> None:
    mcp.tool()(run_workflow)
    mcp.tool()(get_task_status)
    mcp.tool()(resume_workflow)
