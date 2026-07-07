import os
import sys
from loguru import logger


def setup_langsmith():
    """Validates required LangSmith env vars are present at startup."""
    langsmith_tracing = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
    api_key = os.getenv("LANGSMITH_API_KEY")
    project = os.getenv("LANGSMITH_PROJECT")

    if langsmith_tracing:
        if not api_key:
            logger.error("LANGSMITH_TRACING is true but LANGSMITH_API_KEY is missing")
            sys.exit(1)
        if not project:
            logger.error("LANGSMITH_TRACING is true but LANGSMITH_PROJECT is missing")
            sys.exit(1)
        logger.info(f"LangSmith tracing enabled for project: {project}")
    else:
        logger.warning("LANGSMITH_TRACING is not true. LangSmith tracing is disabled.")


if __name__ == "__main__":
    setup_langsmith()
