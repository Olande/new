import asyncio
import sys

from dotenv import load_dotenv
from langsmith import Client, aevaluate
from loguru import logger

from app.core.config.settings import settings
from app.evaluation.constants import DEFAULT_SEARCH_PARAMS, RETRIEVAL_DATASET
from app.evaluation.evaluators import RETRIEVAL_EVALUATORS
from app.evaluation.regression import check_retrieval_regression
from app.evaluation.targets import retrieval_target

_ = load_dotenv()


async def run_evaluations() -> None:
    if not settings.langsmith_api_key:
        logger.error("LANGSMITH_API_KEY not set. Cannot run evaluations.")
        sys.exit(1)

    client = Client()
    params = DEFAULT_SEARCH_PARAMS
    logger.info(
        "Running retrieval evaluation on dataset={} with params={}",
        RETRIEVAL_DATASET,
        params.as_dict(),
    )

    async def target(inputs: dict) -> dict:
        return await retrieval_target(inputs, params=params)

    retrieval_results = await aevaluate(
        target,
        data=RETRIEVAL_DATASET,
        evaluators=RETRIEVAL_EVALUATORS,
        experiment_prefix="hybrid-retrieval",
        metadata={"search_params": params.as_dict(), "dataset": RETRIEVAL_DATASET},
    )

    has_error = False
    try:
        has_error = check_retrieval_regression(
            client, retrieval_results.experiment_name
        )
    except Exception as e:
        logger.warning(f"Error comparing retrieval metrics: {e}")

    logger.info("Evaluations completed.")
    if has_error:
        sys.exit(1)


def main() -> None:
    asyncio.run(run_evaluations())


if __name__ == "__main__":
    main()
