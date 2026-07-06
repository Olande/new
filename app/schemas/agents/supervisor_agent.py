from typing import Literal
from pydantic import BaseModel, Field


class SupervisorDecision(BaseModel):
    reasoning: str = Field(
        description=(
            "One short sentence (5-15 words) explaining the immediate reason "
            "for the routing decision."
        )
    )

    next_subgraph: Literal[
        "discovery_subgraph",
        "memory_subgraph",
        "matching_subgraph",
        "generation_subgraph",
        "tracker_subgraph",
        "__end__",
    ] = Field(description="The single next subgraph to execute.")
