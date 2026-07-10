from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.application import Application


class ApplicationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, application_id: uuid.UUID) -> Application | None:
        """Retrieves an application draft by UUID."""
        return await self.session.get(Application, application_id)

    async def create(self, app_row: Application) -> Application:
        """Saves a new application draft or record into the session."""
        self.session.add(app_row)
        await self.session.flush()
        return app_row

    async def get_latest_for_user_and_job(
        self, user_id: uuid.UUID, job_id: uuid.UUID
    ) -> Application | None:
        """Queries the latest application row matching a user and job ID."""
        q = await self.session.execute(
            select(Application)
            .where(Application.user_id == user_id, Application.job_id == job_id)
            .order_by(Application.created_at.desc())
            .limit(1)
        )
        return q.scalar_one_or_none()
