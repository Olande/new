from fastapi import FastAPI
from prometheus_client import make_asgi_app
from loguru import logger
from app.observability.metrics import init_metrics
from app.observability.langsmith_setup import setup_langsmith

# FastMCP Server (which manages our Tools)
from mcp_server import mcp

app = FastAPI(title="CareerPilot Main Server")

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.on_event("startup")
async def startup_event():
    logger.info("Starting up FastAPI application")
    setup_langsmith()
    init_metrics()


# FastMCP's sse_app is actually a bound method or property returning Starlette app.
app.mount("/mcp", mcp.sse_app())

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
