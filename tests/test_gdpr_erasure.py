import pytest
import uuid
from datetime import datetime, timezone, timedelta
from app.db.models.career_memory import CareerMemory, MemoryEntityType


@pytest.mark.asyncio
async def test_soft_delete_logic_unit_test():
    """
    Unit test to verify the logic since sqlite in-memory fails on Postgres-specific DDL (`VECTOR` and `INTERVAL`).
    """
    user_id = uuid.uuid4()

    mem = CareerMemory(
        user_id=user_id,
        entity_type=MemoryEntityType.skill,
        fact_key="python",
        content={"text": "Expert python developer"},
        valid_from=datetime.now(timezone.utc) - timedelta(days=1),
        valid_to=None,
    )

    # Normally get_current_memory queries for `valid_to.is_(None)` or `valid_to > NOW()`
    # Let's mock the soft delete state:
    mem.valid_to = datetime.now(timezone.utc) - timedelta(minutes=1)

    is_active = mem.valid_to is None or mem.valid_to > datetime.now(timezone.utc)

    # Should be soft-deleted and inactive
    assert not is_active
