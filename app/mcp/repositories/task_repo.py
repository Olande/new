from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.agent_task import AgentTask


class AgentTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, task_id: uuid.UUID) -> AgentTask | None:
        """Retrieves an agent task by its UUID."""
        return await self.session.get(AgentTask, task_id)

    async def create(self, task_row: AgentTask) -> AgentTask:
        """Saves a new agent task into the database session."""
        self.session.add(task_row)
        await self.session.flush()
        return task_row
