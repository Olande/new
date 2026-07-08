import uuid

from mcp.server.fastmcp import FastMCP

from app.api.schemas import (
    ErrorResponse,
    GetMemoryResponse,
    MemoryData,
    StoreMemoryResponse,
)
from app.core.db.base import async_session
from app.features.memory.models import MemoryEntityType
from app.features.memory.schemas import MemoryFactWrite
from app.features.memory.services import get_current_memory, write_memory_facts


async def store_memory(
    user_id: str,
    entity_type: str,
    fact_key: str,
    content: str,
) -> StoreMemoryResponse | ErrorResponse:
    """Store a career memory fact."""
    fact = MemoryFactWrite(
        entity_type=MemoryEntityType(entity_type),
        fact_key=fact_key,
        content={"text": content},
    )
    async with async_session() as session, session.begin():
        rows = await write_memory_facts(
            session, user_id=uuid.UUID(user_id), facts=[fact], commit=False
        )

    if not rows:
        return ErrorResponse(error="Failed to store memory")

    return StoreMemoryResponse(
        id=str(rows[0].id),
        entity_type=rows[0].entity_type,
        fact_key=rows[0].fact_key,
        content=rows[0].content,
    )


async def get_memory(
    user_id: str,
    entity_type: str | None = None,
    fact_key: str | None = None,
) -> GetMemoryResponse:
    """Read career memory facts for a user."""
    async with async_session() as session:
        rows = await get_current_memory(session, user_id=uuid.UUID(user_id))

    if entity_type:
        rows = [r for r in rows if r.entity_type == entity_type]
    if fact_key:
        rows = [r for r in rows if r.fact_key == fact_key]

    return GetMemoryResponse(
        user_id=user_id,
        memories=[
            MemoryData(
                id=str(r.id),
                entity_type=r.entity_type,
                fact_key=r.fact_key,
                content=r.content,
                valid_from=str(r.valid_from) if r.valid_from else None,
            )
            for r in rows
        ],
    )


def register_memory_endpoints(mcp: FastMCP) -> None:
    mcp.tool()(store_memory)
    mcp.tool()(get_memory)
