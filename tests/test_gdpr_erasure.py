import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.career_memory import CareerMemory, MemoryEntityType


@pytest.mark.asyncio
async def test_soft_delete_logic_unit_test():
    user_id = uuid.uuid4()

    mem = CareerMemory(
        user_id=user_id,
        entity_type=MemoryEntityType.skill,
        fact_key="python",
        content={"text": "Expert python developer"},
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_to=None,
    )

    mem.valid_to = datetime.now(UTC) - timedelta(minutes=1)

    is_active = mem.valid_to is None or mem.valid_to > datetime.now(UTC)

    assert not is_active
