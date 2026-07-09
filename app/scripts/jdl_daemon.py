# scripts/jdl_daemon.py
import asyncio
import logging

from app.core.db.base import async_session
from app.core.jdl.discovery import run_discovery
from app.core.jdl.seed_criteria import DISCOVERY_SEED_CRITERIA

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jdl_daemon")

INTERVAL_SECONDS = 43200


async def run_ingestion_cycle() -> None:
    async with async_session() as db:
        all_seen_ids: set[str] = set()
        for criteria in DISCOVERY_SEED_CRITERIA:
            try:
                result = await run_discovery(
                    db=db,
                    criteria=criteria,
                    source_name="primary",
                    seen_source_job_ids=all_seen_ids,
                )
                logger.info(
                    "seed=%s created=%d updated=%d closed=%d",
                    criteria.model_dump(exclude_none=True),
                    result.jobs_created,
                    result.jobs_updated,
                    result.jobs_closed,
                )
            except Exception:
                logger.exception(
                    "seed failed: %s", criteria.model_dump(exclude_none=True)
                )
                continue


async def daemon_loop() -> None:
    while True:
        try:
            await run_ingestion_cycle()
        except Exception:
            logger.exception("ingestion cycle failed entirely")
        await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(daemon_loop())
