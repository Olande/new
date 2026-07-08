import asyncio
import os
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI
from loguru import logger
from prometheus_client import make_asgi_app

# FastMCP Server
from app.api.mcp_server import mcp
from app.core.db.base import async_session
from app.core.llm.embeddings import refresh_stale_embeddings
from app.core.observability.langsmith_setup import setup_langsmith
from app.core.observability.metrics import init_metrics


async def schedule_embeddings_refresh():
    logger.info("Starting scheduled embeddings refresh task (runs every 24h)")
    while True:
        try:
            await asyncio.sleep(24 * 3600)
            logger.info("Running scheduled refresh of stale embeddings...")
            async with async_session() as session:
                await refresh_stale_embeddings(session)
        except asyncio.CancelledError:
            logger.info("Scheduled embeddings refresh task cancelled")
            break
        except Exception as e:
            logger.exception(f"Error during scheduled embeddings refresh: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FastAPI application")
    setup_langsmith()
    init_metrics()
    refresh_task = asyncio.create_task(schedule_embeddings_refresh())
    yield
    logger.info("Shutting down FastAPI application")
    refresh_task.cancel()
    with suppress(asyncio.CancelledError):
        await refresh_task


app = FastAPI(title="CareerPilot Main Server", lifespan=lifespan)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

app.mount("/mcp", mcp.sse_app())


@app.get("/")
async def root():
    return {"status": "ok", "message": "CareerPilot Main Server is running"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),  # nosec B104 - required for Docker/container networking
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
