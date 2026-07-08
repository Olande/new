import time

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from loguru import logger
from psycopg_pool import AsyncConnectionPool

from app.core.config.settings import settings
from app.core.observability.metrics import agent_latency, run_completions, run_failures
from app.features.applications.resume_agent import generation_graph
from app.features.applications.tracker_agent import tracker_graph
from app.features.jobs.agent import discovery_graph
from app.features.matching.agent import matching_graph
from app.features.memory.agent import memory_graph
from app.features.workflows.graph_state import CareerPilotState
from app.features.workflows.responder import responder_agent
from app.features.workflows.supervisor import supervisor_agent


class PrometheusMetricsCallbackHandler(BaseCallbackHandler):
    """Callback handler to record Prometheus metrics for LangGraph runs."""

    def __init__(self):
        super().__init__()
        self._start_times = {}

    def on_chain_start(self, serialized, inputs, **kwargs):
        run_id = kwargs.get("run_id")
        name = serialized.get("name") or "unnamed_chain"
        self._start_times[run_id] = (name, time.time())

    def on_chain_end(self, outputs, **kwargs):
        run_id = kwargs.get("run_id")
        if run_id in self._start_times:
            name, start_time = self._start_times.pop(run_id)
            duration = time.time() - start_time
            agent_latency.labels(agent_name=name).observe(duration)
            stage = (
                outputs.get("stage", "unknown")
                if isinstance(outputs, dict)
                else "unknown"
            )
            run_completions.labels(stage=stage).inc()

    def on_chain_error(self, error, **kwargs):
        run_id = kwargs.get("run_id")
        if run_id in self._start_times:
            name, start_time = self._start_times.pop(run_id)
            duration = time.time() - start_time
            agent_latency.labels(agent_name=name).observe(duration)
            run_failures.labels(stage="unknown").inc()


builder = StateGraph(CareerPilotState)
builder.add_node("supervisor", supervisor_agent)
builder.add_node("discovery_subgraph", discovery_graph)
builder.add_node("memory_subgraph", memory_graph)
builder.add_node("matching_subgraph", matching_graph)
builder.add_node("generation_subgraph", generation_graph)
builder.add_node("tracker_subgraph", tracker_graph)
builder.add_node("responder", responder_agent)

builder.add_edge(START, "supervisor")
builder.add_edge("discovery_subgraph", "responder")
builder.add_edge("memory_subgraph", "responder")
builder.add_edge("matching_subgraph", "responder")
builder.add_edge("generation_subgraph", "responder")
builder.add_edge("tracker_subgraph", "responder")
builder.add_edge("responder", END)


graph = builder.compile()


async def get_master_graph(pool: AsyncConnectionPool | None = None):
    """Returns the graph compiled with a Postgres checkpointer."""
    if pool is None:
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
