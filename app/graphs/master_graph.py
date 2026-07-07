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

builder = StateGraph(CareerPilotState)


builder.add_node("supervisor", supervisor_agent)
builder.add_node("discovery_subgraph", discovery_graph)
builder.add_node("memory_subgraph", memory_graph)
builder.add_node("matching_subgraph", matching_graph)
builder.add_node("generation_subgraph", generation_graph)
builder.add_node("tracker_subgraph", tracker_graph)

builder.add_edge(START, "supervisor")

builder.add_edge("discovery_subgraph", "supervisor")
builder.add_edge("memory_subgraph", "supervisor")
builder.add_edge("matching_subgraph", "supervisor")
builder.add_edge("generation_subgraph", "supervisor")
builder.add_edge("tracker_subgraph", "supervisor")


master_graph_instance = None
compile_lock = asyncio.Lock()


async def get_master_graph():
    """Return the singleton compiled LangGraph instance."""
    global master_graph_instance

    if master_graph_instance is not None:
        return master_graph_instance

    async with compile_lock:
        if master_graph_instance is None:
            logger.info("Compiling LangGraph with PostgreSQL checkpointer.")

            checkpointer = await get_checkpointer()

            master_graph_instance = builder.compile(checkpointer=checkpointer)

    return master_graph_instance
