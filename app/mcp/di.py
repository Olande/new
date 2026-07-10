from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base import async_session
from app.mcp.exceptions import UnauthorizedError
from app.mcp.mcp_context import get_current_tenant_id, get_current_user_id


class AuthenticatedUser:
    def __init__(self, user_id: uuid.UUID, tenant_id: uuid.UUID):
        self.user_id = user_id
        self.tenant_id = tenant_id


def require_user() -> AuthenticatedUser:
    """Retrieves the authenticated user from the active request context, or raises UnauthorizedError."""
    uid = get_current_user_id()
    tid = get_current_tenant_id()
    if not uid:
        raise UnauthorizedError("Authentication token is missing or invalid")
    try:
        user_uuid = uuid.UUID(uid)
        tenant_uuid = uuid.UUID(tid) if tid else user_uuid
        return AuthenticatedUser(user_id=user_uuid, tenant_id=tenant_uuid)
    except ValueError as e:
        raise UnauthorizedError("Invalid user identity format") from e


@asynccontextmanager
async def db_session_scope() -> AsyncGenerator[AsyncSession]:
    """Yields a database session scoped for repository operations, committing on success."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
