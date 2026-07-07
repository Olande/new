from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from prometheus_client import make_asgi_app

from app.observability.langsmith_setup import setup_langsmith
from app.observability.metrics import init_metrics

# FastMCP Server
from mcp_server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FastAPI application")
    setup_langsmith()
    init_metrics()
    yield
    logger.info("Shutting down FastAPI application")


app = FastAPI(title="CareerPilot Main Server", lifespan=lifespan)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

app.mount("/mcp", mcp.sse_app())


@app.get("/")
async def root():
    return {"status": "ok", "message": "CareerPilot Main Server is running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
