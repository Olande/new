import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_task import AgentTask


async def create_task(
    session: AsyncSession,
    *,
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
