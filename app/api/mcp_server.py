from mcp.server.fastmcp import FastMCP

from app.features.jobs.api import register_job_endpoints
from app.features.memory.api import register_memory_endpoints
from app.features.workflows.api import register_workflow_endpoints

# MCP Server
mcp = FastMCP("CareerPilot", log_level="INFO")

# Register Feature Endpoints
register_job_endpoints(mcp)
register_memory_endpoints(mcp)
register_workflow_endpoints(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
