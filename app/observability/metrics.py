import time
from loguru import logger
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import event
from sqlalchemy.engine import Engine

# Counters
run_completions = Counter(
    "careerpilot_run_completions_total",
    "Total number of completed agent runs",
    ["stage"],
)

run_failures = Counter(
    "careerpilot_run_failures_total", "Total number of failed agent runs", ["stage"]
)

# Histograms
agent_latency = Histogram(
    "careerpilot_agent_latency_seconds", "Time spent in an agent run", ["agent_name"]
)

query_duration = Histogram(
    "careerpilot_db_query_duration_seconds",
    "Time spent executing DB queries",
    ["query_type"],
)

# Gauges
current_tasks = Gauge("careerpilot_current_tasks", "Number of tasks currently running")


# SQLAlchemy Event Hooks
@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()


@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - context._query_start_time
    # Classify query type briefly based on the statement string
    q_type = "unknown"
    stmt_lower = statement.lower().strip()
    if stmt_lower.startswith("select"):
        q_type = "select"
    elif stmt_lower.startswith("insert"):
        q_type = "insert"
    elif stmt_lower.startswith("update"):
        q_type = "update"
    elif stmt_lower.startswith("delete"):
        q_type = "delete"

    # Optional: you could make this more granular like checking for "hybrid_search" or "career_memory"
    if "pg_vector" in stmt_lower or "job" in stmt_lower and q_type == "select":
        q_type = "select_search"

    query_duration.labels(query_type=q_type).observe(total)


def init_metrics():
    logger.info("Initialized Prometheus metrics definitions and SQLAlchemy hooks.")
