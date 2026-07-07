from dotenv import load_dotenv
from loguru import logger

from app.config.settings import settings

_ = load_dotenv()


def setup_langsmith() -> None:
    if settings.langsmith_tracing:
        logger.info(
            f"LangSmith tracing enabled for project: {settings.langsmith_project}"
        )
    else:
        logger.warning("LANGSMITH_TRACING is not true. LangSmith tracing is disabled.")
