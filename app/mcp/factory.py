from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base import async_session


async def with_service[T, U](
    service_factory: Callable[[AsyncSession], T],
    action: Callable[[T], Awaitable[U]],
) -> U:
    async with async_session() as session:
        service = service_factory(session)
        return await action(service)
