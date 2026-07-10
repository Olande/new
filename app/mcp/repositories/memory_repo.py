from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.memory import CareerMemory


class CareerMemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_memories_by_user_id(
        self, user_id: uuid.UUID
    ) -> Sequence[CareerMemory]:
        """Queries all career memory rows matching a specific user UUID."""
        q = await self.session.execute(
            select(CareerMemory).where(CareerMemory.user_id == user_id)
        )
        return q.scalars().all()
