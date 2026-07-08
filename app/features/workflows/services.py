import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.workflows.repository import create_agent_task


async def create_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    graph_name: str,
    payload: dict,
):
    return await create_agent_task(
        session=session,
        user_id=user_id,
        graph_name=graph_name,
        payload=payload,
    )
