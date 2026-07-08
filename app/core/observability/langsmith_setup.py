import os

from dotenv import load_dotenv
from loguru import logger

from app.core.config.settings import settings

_ = load_dotenv()


def setup_langsmith() -> None:
    if settings.langsmith_tracing:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key or ""
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project or ""
        logger.info(
            f"LangSmith tracing enabled for project: {settings.langsmith_project}"
        )
    else:
        logger.warning("LANGSMITH_TRACING is not true. LangSmith tracing is disabled.")
