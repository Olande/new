import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from loguru import logger
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config.settings import settings

db_url = settings.database_url.replace("+asyncpg", "")

connection_kwargs = {
    "autocommit": True,
    "prepare_threshold": 0,
    "row_factory": dict_row,
}

pool: AsyncConnectionPool = AsyncConnectionPool(
    conninfo=db_url,
    max_size=10,
    kwargs=connection_kwargs,
    open=False,
)

checkpointer_instance: AsyncPostgresSaver | None = None
pool_open = False
is_initialized = False

init_lock = asyncio.Lock()


async def get_checkpointer() -> AsyncPostgresSaver:
    global checkpointer_instance, pool_open, is_initialized

    async with init_lock:
        if not pool_open:
            logger.info("Opening PostgreSQL connection pool.")
            await pool.open()
            pool_open = True

        if checkpointer_instance is None:
            logger.info("Creating AsyncPostgresSaver.")
            checkpointer_instance = AsyncPostgresSaver(pool)

        if not is_initialized:
            logger.info("Initializing LangGraph checkpoint tables.")
            await checkpointer_instance.setup()
            is_initialized = True

    return checkpointer_instance


async def close_checkpointer() -> None:
    """
    Gracefully close the PostgreSQL connection pool.
    """
    global checkpointer_instance, pool_open, is_initialized

    async with init_lock:
        if pool_open:
            logger.info("Closing PostgreSQL connection pool.")
            await pool.close()

        checkpointer_instance = None
        pool_open = False
        is_initialized = False
