import functools
import time

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import START, StateGraph
from loguru import logger
from psycopg_pool import AsyncConnectionPool

from app.agents.discovery_agent import discovery_graph
from app.agents.matching_agent import matching_graph
from app.agents.memory_agent import memory_graph
from app.agents.resume_agent import generation_graph
from app.agents.supervisor import supervisor_agent
from app.agents.tracker_agent import tracker_graph
from app.config.settings import settings
from app.observability.metrics import agent_latency, run_completions, run_failures
from app.schemas.graph_state import CareerPilotState


def track_metrics_wrapper(func, agent_name):
    """Wraps an agent execution to track latency and completion/failure."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()

        # Try to extract state for metric tagging
        state = kwargs.get("state")
        if state is None and len(args) > 0:
            state = args[0]

        stage = state.get("stage", "unknown") if isinstance(state, dict) else "unknown"

        try:
            result = await func(*args, **kwargs)
            agent_latency.labels(agent_name=agent_name).observe(time.time() - start)
            run_completions.labels(stage=stage).inc()
            return result
        except Exception as e:
            agent_latency.labels(agent_name=agent_name).observe(time.time() - start)
            run_failures.labels(stage=stage).inc()
            logger.error(f"Agent {agent_name} failed: {e}")
            raise e

    return wrapper


wrapped_discovery = track_metrics_wrapper(discovery_graph.ainvoke, "discovery")
wrapped_memory = track_metrics_wrapper(memory_graph.ainvoke, "memory")
wrapped_matching = track_metrics_wrapper(matching_graph.ainvoke, "matching")
wrapped_generation = track_metrics_wrapper(generation_graph.ainvoke, "generation")
wrapped_tracker = track_metrics_wrapper(tracker_graph.ainvoke, "tracker")
wrapped_supervisor = track_metrics_wrapper(supervisor_agent, "supervisor")


builder = StateGraph(CareerPilotState)
builder.add_node("supervisor", wrapped_supervisor)
builder.add_node("discovery_subgraph", wrapped_discovery)
builder.add_node("memory_subgraph", wrapped_memory)
builder.add_node("matching_subgraph", wrapped_matching)
builder.add_node("generation_subgraph", wrapped_generation)
builder.add_node("tracker_subgraph", wrapped_tracker)
builder.add_edge(START, "supervisor")


graph = builder.compile()


async def get_master_graph():
    """Returns the graph compiled with a Postgres checkpointer."""
    pool = AsyncConnectionPool(
        conninfo=settings.postgres_url.replace("postgresql+psycopg", "postgresql"),
        max_size=5,
    )

    try:
        await pool.wait()
    except Exception as e:
        logger.warning(f"Connection pool not ready immediately: {e}")

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    return builder.compile(checkpointer=checkpointer)
