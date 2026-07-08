import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.workflows.models import AgentTask


async def create_agent_task(
    session: AsyncSession,
    user_id: uuid.UUID,
    graph_name: str,
    payload: dict,
) -> AgentTask:
    task_uuid = uuid.uuid4()
    thread_id = f"user:{user_id}:task:{task_uuid}"

    if "user_id" not in payload:
        payload["user_id"] = str(user_id)
    if "thread_id" not in payload:
        payload["thread_id"] = thread_id

    task = AgentTask(
        id=task_uuid,
        thread_id=thread_id,
        graph_name=graph_name,
        status="pending",
        payload=payload,
    )
    session.add(task)
    await session.flush()
    return task


async def get_task_repo(session: AsyncSession, task_id: uuid.UUID) -> AgentTask | None:
    return await session.get(AgentTask, task_id)


async def resume_task_repo(
    session: AsyncSession, task_id: uuid.UUID, resume_data: dict
) -> AgentTask:
    task = await session.get(AgentTask, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")
    if task.status != "paused":
        raise ValueError(f"Task {task_id} is not paused (status: {task.status})")

    # Update payload with resume data
    new_payload = task.payload.copy() if task.payload else {}
    new_payload["resume_data"] = resume_data
    task.payload = new_payload

    # Reset task to pending so the worker picks it up
    task.status = "pending"
    task.locked_at = None
    task.locked_by = None
    return task
