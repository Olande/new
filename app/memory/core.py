# Memory
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.career_memory import CareerMemory, MemoryEntityType
from app.schemas.career_memory import MemoryFactWrite


async def write_memory_facts(
    session: AsyncSession,
    user_id: uuid.UUID,
    facts: list[MemoryFactWrite],
    *,
    commit: bool = True,
) -> list[CareerMemory]:
    if not facts:
        return []

    deduplicated = {(f.entity_type, f.fact_key): f for f in facts}
    facts = list(deduplicated.values())

    now = datetime.now(UTC)
    keys = [(fact.entity_type, fact.fact_key) for fact in facts]

    await session.execute(
        update(CareerMemory)
        .where(
            CareerMemory.user_id == user_id,
            tuple_(CareerMemory.entity_type, CareerMemory.fact_key).in_(keys),
            CareerMemory.valid_to.is_(None),
        )
        .values(valid_to=now)
    )

    new_rows = [
        CareerMemory(
            user_id=user_id,
            entity_type=fact.entity_type,
            fact_key=fact.fact_key,
            content=fact.content,
            valid_from=now,
            valid_to=None,
        )
        for fact in facts
        if fact.content is not None
    ]
    session.add_all(new_rows)
    await session.flush()

    if commit:
        await session.commit()

    return new_rows


async def write_memory_fact(
    session: AsyncSession,
    user_id: uuid.UUID,
    entity_type: MemoryEntityType,
    fact_key: str,
    content: dict | None,
    *,
    commit: bool = True,
) -> CareerMemory | None:
    results = await write_memory_facts(
        session=session,
        user_id=user_id,
        facts=[
            MemoryFactWrite(
                entity_type=entity_type, fact_key=fact_key, content=content
            ),
        ],
        commit=commit,
    )
    return results[0] if results else None


async def get_current_memory(
    session: AsyncSession,
    user_id: uuid.UUID,
    as_of: datetime | None = None,
) -> list[CareerMemory]:
    if as_of is None:
        as_of = datetime.now(UTC)
    elif as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    result = await session.execute(
        select(CareerMemory)
        .where(
            CareerMemory.user_id == user_id,
            CareerMemory.valid_from < as_of,
            CareerMemory.valid_to.is_(None) | (CareerMemory.valid_to > as_of),
        )
        .order_by(CareerMemory.entity_type, CareerMemory.fact_key)
    )

    return result.scalars().all()
