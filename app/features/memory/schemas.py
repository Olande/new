from typing import Literal

from pydantic import BaseModel, Field

from app.features.memory.models import MemoryEntityType


class MemoryFactWrite(BaseModel):
    """One fact to write. content=None means soft-delete this fact_key."""

    entity_type: MemoryEntityType
    fact_key: str
    content: dict | None


class ExtractedFact(BaseModel):
    entity_type: Literal[
        "skill", "employment_history", "project", "achievement", "education"
    ]
    fact_key: str = Field(
        description="snake_case key for the fact, e.g. python_developer or target_industry"
    )
    content: str = Field(description="The memory content text summarizing the fact")


class ExtractedFactsList(BaseModel):
    facts: list[ExtractedFact]
