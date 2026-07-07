from langgraph.graph import StateGraph, START
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from loguru import logger
from psycopg_pool import AsyncConnectionPool

from app.schemas.graph_state import CareerPilotState
from app.config.settings import settings
from app.agents.supervisor import supervisor_agent
from app.agents.discovery_agent import discovery_graph
from app.agents.memory_agent import memory_graph
from app.agents.matching_agent import matching_graph
from app.agents.resume_agent import generation_graph
from app.agents.tracker_agent import tracker_graph
from app.observability.metrics import run_completions, run_failures, agent_latency
import time


def track_metrics_wrapper(func, agent_name):
    """Wraps an agent execution to track latency and completion/failure via Prometheus."""

    async def wrapper(state, config=None, *args, **kwargs):
        start = time.time()
        stage = state.get("stage", "unknown") if isinstance(state, dict) else "unknown"
        try:
            # We must pass the config through so that tags/metadata for LangSmith flow correctly
            if config:
                result = await func(state, config=config, *args, **kwargs)
            else:
                result = await func(state, *args, **kwargs)
            agent_latency.labels(agent_name=agent_name).observe(time.time() - start)
            run_completions.labels(stage=stage).inc()
            return result
        except Exception as e:
            agent_latency.labels(agent_name=agent_name).observe(time.time() - start)
            run_failures.labels(stage=stage).inc()
            logger.error(f"Agent {agent_name} failed: {e}")
            raise e

    return wrapper


# Wrap the graphs to capture latency and success/failure metrics
wrapped_discovery = track_metrics_wrapper(discovery_graph.ainvoke, "discovery")
wrapped_memory = track_metrics_wrapper(memory_graph.ainvoke, "memory")
wrapped_matching = track_metrics_wrapper(matching_graph.ainvoke, "matching")
wrapped_generation = track_metrics_wrapper(generation_graph.ainvoke, "generation")
wrapped_tracker = track_metrics_wrapper(tracker_graph.ainvoke, "tracker")
wrapped_supervisor = track_metrics_wrapper(supervisor_agent, "supervisor")


async def get_master_graph():
    builder = StateGraph(CareerPilotState)

    builder.add_node("supervisor", wrapped_supervisor)
    builder.add_node("discovery_subgraph", wrapped_discovery)
    builder.add_node("memory_subgraph", wrapped_memory)
    builder.add_node("matching_subgraph", wrapped_matching)
    builder.add_node("generation_subgraph", wrapped_generation)
    builder.add_node("tracker_subgraph", wrapped_tracker)

    builder.add_edge(START, "supervisor")

    pool = AsyncConnectionPool(
        conninfo=settings.postgres_url.replace("postgresql+psycopg", "postgresql"),
        max_size=5,
    )

    # Optional wait for pool ready
    try:
        await pool.wait()
    except Exception as e:
        logger.warning(f"Connection pool not ready immediately: {e}")

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    return builder.compile(checkpointer=checkpointer)
