from typing import Literal
from pydantic import BaseModel, Field


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
