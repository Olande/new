from langgraph.types import Command
from loguru import logger

from app.features.workflows.graph_state import CareerPilotState


async def normalization_agent(state: CareerPilotState) -> Command:
    logger.info("Normalization agent starting")
    discovered_job_ids = state.get("discovered_job_ids") or []

    unique_ids = list(dict.fromkeys(discovered_job_ids))

    logger.info(
        f"Consolidated {len(unique_ids)} unique discovered job IDs (removed {len(discovered_job_ids) - len(unique_ids)} duplicates)."
    )

    return Command(
        graph=Command.PARENT,
        goto="supervisor",
        update={"discovered_job_ids": unique_ids, "stage": "memory"},
    )
