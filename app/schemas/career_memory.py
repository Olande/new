from pydantic import BaseModel

from app.db.models.career_memory import MemoryEntityType


class MemoryFactWrite(BaseModel):
    """One fact to write. content=None means soft-delete this fact_key."""

    entity_type: MemoryEntityType
    fact_key: str
    content: dict | None
