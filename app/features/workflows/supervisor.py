from typing import Literal

from langgraph.types import Command
from loguru import logger

from app.features.workflows.graph_state import CareerPilotState


def deterministic_route(state: CareerPilotState) -> tuple[str, str]:
    """Deterministic routing based on current stage and history."""
    stage = state.get("stage")
    stage_routes = {
        "memory": "memory_subgraph",
        "matching": "matching_subgraph",
        "generation": "generation_subgraph",
        "tracker": "tracker_subgraph",
        "completed": "responder",
    }
    if stage in stage_routes:
        return stage_routes[stage], f"Route by stage: {stage}"

    # Avoid infinite loops: check if discovery already ran
    routing_history = state.get("routing_history") or []
    has_discovery_run = any("discovery" in entry for entry in routing_history)
    discovered_jobs = state.get("discovered_job_ids") or []

    # If discovery ran but returned no jobs, end the workflow
    if has_discovery_run and not discovered_jobs:
        return "responder", "Discovery completed with no jobs"

    # If discovery hasn't run yet, default to starting discovery
    if not has_discovery_run:
        return "discovery_subgraph", "Start discovery phase"

    return "responder", "Default end workflow"


async def supervisor_agent(
    state: CareerPilotState,
) -> Command[
    Literal[
        "discovery_subgraph",
        "memory_subgraph",
        "matching_subgraph",
        "generation_subgraph",
        "tracker_subgraph",
        "responder",
    ]
]:
    logger.info("Supervisor evaluating workflow state deterministically.")

    current_history = state.get("routing_history") or []

    target, reason = deterministic_route(state)

    logger.info(
        "Supervisor selected '{}'. Reason: {}",
        target,
        reason,
    )

    new_history = current_history + [f"supervisor -> {target}"]
    return Command(
        goto=target,
        update={
            "routing_history": new_history,
            "supervisor_reasoning": reason,
        },
    )
