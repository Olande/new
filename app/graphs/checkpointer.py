import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from loguru import logger
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config.settings import settings

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

_checkpointer: AsyncPostgresSaver | None = None
_pool_open = False
_initialized = False

_init_lock = asyncio.Lock()


async def get_checkpointer() -> AsyncPostgresSaver:

    global _checkpointer, _pool_open, _initialized

    async with _init_lock:
        if not _pool_open:
            logger.info("Opening PostgreSQL connection pool.")
            await pool.open()
            _pool_open = True

        if _checkpointer is None:
            logger.info("Creating AsyncPostgresSaver.")
            _checkpointer = AsyncPostgresSaver(pool)

        if not _initialized:
            logger.info("Initializing LangGraph checkpoint tables.")
            await _checkpointer.setup()
            _initialized = True

    return _checkpointer


async def close_checkpointer() -> None:
    """
    Gracefully close the PostgreSQL connection pool.
    """
    global _checkpointer, _pool_open, _initialized

    async with _init_lock:
        if _pool_open:
            logger.info("Closing PostgreSQL connection pool.")
            await pool.close()

        _checkpointer = None
        _pool_open = False
        _initialized = False
