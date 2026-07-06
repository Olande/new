import asyncio

from langgraph.graph import START, StateGraph
from loguru import logger

from app.agents.discovery_agent import discovery_graph
from app.agents.matching_agent import matching_graph
from app.agents.memory_agent import memory_graph
from app.agents.resume_agent import generation_graph
from app.agents.supervisor import supervisor_agent
from app.agents.tracker_agent import tracker_graph
from app.graphs.checkpointer import get_checkpointer
from app.schemas.graph_state import CareerPilotState
from langgraph.errors import ParentCommand
from langgraph.types import Command

builder = StateGraph(CareerPilotState)


async def discovery_node(state: CareerPilotState) -> Command:
    config = {"configurable": {"thread_id": state.get("thread_id")}}
    try:
        res = await discovery_graph.ainvoke(state, config)
        update = {}
        if "discovered_job_ids" in res:
            update["discovered_job_ids"] = list(set(res["discovered_job_ids"] or []))
        if "stage" in res:
            update["stage"] = res["stage"]
    except ParentCommand as pc:
        inner_update = pc.args[0].update or {}
        update = {}
        if "discovered_job_ids" in inner_update:
            update["discovered_job_ids"] = list(
                set(inner_update["discovered_job_ids"] or [])
            )
        if "stage" in inner_update:
            update["stage"] = inner_update["stage"]
    return Command(goto="supervisor", update=update)


async def memory_node(state: CareerPilotState) -> Command:
    config = {"configurable": {"thread_id": state.get("thread_id")}}
    try:
        res = await memory_graph.ainvoke(state, config)
        update = {}
        if "career_memory" in res:
            update["career_memory"] = res["career_memory"]
        if "stage" in res:
            update["stage"] = res["stage"]
    except ParentCommand as pc:
        inner_update = pc.args[0].update or {}
        update = {}
        if "career_memory" in inner_update:
            update["career_memory"] = inner_update["career_memory"]
        if "stage" in inner_update:
            update["stage"] = inner_update["stage"]
    return Command(goto="supervisor", update=update)


async def matching_node(state: CareerPilotState) -> Command:
    config = {"configurable": {"thread_id": state.get("thread_id")}}
    try:
        res = await matching_graph.ainvoke(state, config)
        update = {}
        if "match_scores" in res:
            update["match_scores"] = res["match_scores"]
        if "stage" in res:
            update["stage"] = res["stage"]
    except ParentCommand as pc:
        inner_update = pc.args[0].update or {}
        update = {}
        if "match_scores" in inner_update:
            update["match_scores"] = inner_update["match_scores"]
        if "stage" in inner_update:
            update["stage"] = inner_update["stage"]
    return Command(goto="supervisor", update=update)


async def generation_node(state: CareerPilotState) -> Command:
    config = {"configurable": {"thread_id": state.get("thread_id")}}
    try:
        res = await generation_graph.ainvoke(state, config)
        update = {}
        if "active_application_id" in res:
            update["active_application_id"] = res["active_application_id"]
        if "stage" in res:
            update["stage"] = res["stage"]
    except ParentCommand as pc:
        inner_update = pc.args[0].update or {}
        update = {}
        if "active_application_id" in inner_update:
            update["active_application_id"] = inner_update["active_application_id"]
        if "stage" in inner_update:
            update["stage"] = inner_update["stage"]
    return Command(goto="supervisor", update=update)


async def tracker_node(state: CareerPilotState) -> Command:
    config = {"configurable": {"thread_id": state.get("thread_id")}}
    try:
        res = await tracker_graph.ainvoke(state, config)
        update = {}
        if "application_status" in res:
            update["application_status"] = res["application_status"]
        if "stage" in res:
            update["stage"] = res["stage"]
    except ParentCommand as pc:
        inner_update = pc.args[0].update or {}
        update = {}
        if "application_status" in inner_update:
            update["application_status"] = inner_update["application_status"]
        if "stage" in inner_update:
            update["stage"] = inner_update["stage"]
    return Command(goto="supervisor", update=update)


builder.add_node("supervisor", supervisor_agent)
builder.add_node("discovery_subgraph", discovery_node)
builder.add_node("memory_subgraph", memory_node)
builder.add_node("matching_subgraph", matching_node)
builder.add_node("generation_subgraph", generation_node)
builder.add_node("tracker_subgraph", tracker_node)

builder.add_edge(START, "supervisor")

_master_graph = None
_compile_lock = asyncio.Lock()


async def get_master_graph():
    """Return the singleton compiled LangGraph instance."""
    global _master_graph

    if _master_graph is not None:
        return _master_graph

    async with _compile_lock:
        if _master_graph is None:
            logger.info("Compiling LangGraph with PostgreSQL checkpointer.")

            checkpointer = await get_checkpointer()

            _master_graph = builder.compile(checkpointer=checkpointer)

    return _master_graph
