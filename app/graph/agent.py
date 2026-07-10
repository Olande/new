from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.graph import StateGraph

from app.core.config.settings import settings
from app.graph.graph_state import QAGraphState
from app.graph.nodes import (
    analyze_query,
    compile_results,
    execute_submission,
    generate_draft,
    heuristic_check,
    hybrid_search,
    intent_router,
    llm_critic,
    prepare_submission,
    request_human_approval,
    route_to_scoring,
    score_candidate,
)


def _build_graph(checkpointer: Any, store: Any):
    """Internal builder, expects Postgres checkpointer and store already setup."""
    graph = StateGraph(QAGraphState)
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("intent_router", intent_router)
    graph.add_node("hybrid_search", hybrid_search)
    graph.add_node("score_candidate", score_candidate)
    graph.add_node("compile_results", compile_results)
    graph.add_node("prepare_submission", prepare_submission)
    graph.add_node("request_human_approval", request_human_approval)
    graph.add_node("execute_submission", execute_submission)
    graph.add_node("generate_draft", generate_draft)
    graph.add_node("heuristic_check", heuristic_check)
    graph.add_node("llm_critic", llm_critic)

    graph.set_entry_point("analyze_query")
    graph.add_edge("analyze_query", "intent_router")
    graph.add_conditional_edges("hybrid_search", route_to_scoring, ["score_candidate", "generate_draft"])
    graph.add_edge("score_candidate", "compile_results")
    graph.add_edge("compile_results", "generate_draft")
    graph.add_edge("generate_draft", "heuristic_check")
    graph.add_edge("prepare_submission", "request_human_approval")
    graph.add_edge("execute_submission", "generate_draft")
    # intent_router, heuristic_check, llm_critic, request_human_approval route via Command

    return graph.compile(checkpointer=checkpointer, store=store)


def build_qa_graph(*, checkpointer: Any, store: Any):
    """
    Build graph with Postgres persistence. No in-memory fallback.
    Enforces requirement: checkpointer must be Postgres throughout.
    """
    if checkpointer is None or store is None:
        raise ValueError("Postgres checkpointer and Postgres Store are required. Use build_qa_graph_postgres() or pass async instances.")
    # Quick sanity check for postgres type to prevent accidental MemorySaver usage
    name = type(checkpointer).__name__.lower()
    if "memory" in name or "inmemory" in name:
        raise ValueError(f"Memory checkpointer {name} not allowed. Must be Postgres (AsyncPostgresSaver).")
    return _build_graph(checkpointer, store)


@asynccontextmanager
async def build_qa_graph_postgres(dsn: str | None = None) -> AsyncGenerator[Any]:
    """
    Lean Postgres factory using known libs: langgraph-checkpoint-postgres + psycopg_pool.
    Uses same DB as SQLAlchemy async_session (asyncpg driver) but via psycopg pool for checkpointer.
    CareerMemory table is migrated into Store on first use via nodes.migrate_career_memory_table_to_store.

    Usage:
        async with build_qa_graph_postgres() as graph:
            await graph.ainvoke({"user_query": "...", "user_id": str(uid)}, config={"configurable": {"thread_id": tid}})
    """
    dsn = dsn or getattr(settings, "database_url", None) or getattr(settings, "postgres_dsn", None)
    if not dsn:
        raise ValueError("DATABASE_URL not set in settings. Set settings.database_url for Postgres checkpointer.")

    # Import lazily so CI without postgres deps can still import module
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
        from psycopg_pool import AsyncConnectionPool
    except ImportError as e:
        raise ImportError(f"Postgres deps missing: {e}. Install langgraph-checkpoint-postgres, langgraph-store-postgres, psycopg[binary], psycopg_pool") from e

    # AsyncConnectionPool is the recommended way per langgraph docs (handles concurrency)
    # autocommit + prepare_threshold=0 avoids prepared statement conflicts with pgbouncer
    checkpointer_pool = AsyncConnectionPool(conninfo=dsn, max_size=20, kwargs={"autocommit": True, "prepare_threshold": 0})
    store_pool = AsyncConnectionPool(conninfo=dsn, max_size=20, kwargs={"autocommit": True, "prepare_threshold": 0})

    await checkpointer_pool.open()
    await store_pool.open()

    checkpointer = AsyncPostgresSaver(checkpointer_pool)
    store = AsyncPostgresStore(store_pool)

    # setup() creates tables: checkpoints, checkpoint_blobs, checkpoint_writes, store, store_vectors
    await checkpointer.setup()
    await store.setup()

    try:
        graph = _build_graph(checkpointer=checkpointer, store=store)
        yield graph
    finally:
        await checkpointer_pool.close()
        await store_pool.close()


# For tests that need sync version without real Postgres, explicitly require passing fake postgres-like objects.
# We do NOT provide Memory fallback here per requirement.
