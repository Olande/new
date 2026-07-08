from typing import Literal

from langgraph.types import Command
from loguru import logger

from app.features.workflows.graph_state import CareerPilotState


def deterministic_route(state: CareerPilotState) -> tuple[str, str, dict]:
    """Deterministic routing based on current stage and history."""
    stage = state.get("stage")
    messages = state.get("messages") or []
    updates = {}

    from langchain_core.messages import HumanMessage

    # Clear state to start fresh on a new user turn or if completed
    is_new_turn = messages and isinstance(messages[-1], HumanMessage)
    if is_new_turn or stage == "completed":
        stage = None
        updates["stage"] = None
        updates["discovered_job_ids"] = ["__CLEAR__"]
        updates["routing_history"] = ["__CLEAR__"]

    stage_routes = {
        "memory": "memory_subgraph",
        "matching": "matching_subgraph",
        "generation": "generation_subgraph",
        "tracker": "tracker_subgraph",
    }
    if stage in stage_routes:
        return stage_routes[stage], f"Route by stage: {stage}", updates

    # Use updated local variables to evaluate has_discovery_run
    local_history = (
        []
        if ("__CLEAR__" in updates.get("routing_history", []))
        else (state.get("routing_history") or [])
    )
    has_discovery_run = any("discovery" in entry for entry in local_history)
    local_discovered_jobs = (
        []
        if ("__CLEAR__" in updates.get("discovered_job_ids", []))
        else (state.get("discovered_job_ids") or [])
    )

    # If discovery ran but returned no jobs, end the workflow
    if has_discovery_run and not local_discovered_jobs:
        return "responder", "Discovery completed with no jobs", updates

    # If discovery hasn't run yet, default to starting discovery
    if not has_discovery_run:
        return "discovery_subgraph", "Start discovery phase", updates

    return "responder", "Default end workflow", updates


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

    target, reason, state_updates = deterministic_route(state)

    logger.info(
        "Supervisor selected '{}'. Reason: {}",
        target,
        reason,
    )

    if "__CLEAR__" in state_updates.get("routing_history", []):
        new_history = ["__CLEAR__", f"supervisor -> {target}"]
    else:
        new_history = current_history + [f"supervisor -> {target}"]

    cmd_updates = {
        "routing_history": new_history,
        "supervisor_reasoning": reason,
    }
    cmd_updates.update(state_updates)

    return Command(
        goto=target,
        update=cmd_updates,
    )
