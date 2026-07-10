import asyncio

from langsmith import Client
from loguru import logger

from app.core.config.settings import settings
from app.core.db.base import async_session
from app.core.db.models.job import Job, JobDescription
from scripts.eval_data import (
    EXAMPLES,
    GOLDEN_JOB_IDS,
    GOLDEN_JOBS,
)
from scripts.eval_data import (
    dedup_hash as _dedup_hash,
)


async def seed_golden_jobs() -> dict:
    async with async_session() as session:
        for job_data in GOLDEN_JOBS:
            job_id = GOLDEN_JOB_IDS[job_data["key"]]
            existing = await session.get(Job, job_id)
            if existing is not None:
                continue

            job = Job(
                id=job_id,
                dedup_hash=_dedup_hash(job_id),
                title=job_data["title"],
                company_name=job_data["company_name"],
                required_skills=job_data["required_skills"],
            )
            session.add(job)
            session.add(
                JobDescription(job_id=job_id, cleaned_text=job_data["description"])
            )

        await session.commit()

        from app.core.llm.embeddings import refresh_stale_embeddings

        logger.info("Generating embeddings for golden jobs...")
        await refresh_stale_embeddings(session)

    logger.info("Seeded golden jobs and generated embeddings.")
    return GOLDEN_JOB_IDS


def seed_matching_dataset(
    client: Client, job_ids: dict, *, force: bool = False
) -> None:
    """Create (or optionally recreate) the LangSmith matching eval dataset."""
    dataset_name = "careerpilot-matching-eval-v2"

    existing = None
    try:
        existing = client.read_dataset(dataset_name=dataset_name)
    except Exception:
        existing = None

    if existing is not None and not force:
        logger.info(
            f"Dataset '{dataset_name}' already exists (id={existing.id}). "
            "Pass force=True to wipe and re-seed."
        )
        return

    if existing is not None and force:
        logger.warning(f"Deleting existing dataset '{dataset_name}' for re-seed...")
        client.delete_dataset(dataset_id=existing.id)

    logger.info(f"Creating dataset '{dataset_name}'...")
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description=(
            "Query-style-tagged golden set: exact_terms / paraphrase / "
            "distractor / no_match. no_match examples have expected_job_id=null "
            "and must be excluded from nDCG/RR aggregates "
            "(see app.evaluation.metrics)."
        ),
    )

    inputs = [{"query": ex["query"]} for ex in EXAMPLES]
    outputs = [
        {
            "expected_job_id": str(job_ids[ex["job"]]) if ex["job"] else None,
            "relevance": 1 if ex["job"] else 0,
            "query_style": ex["style"],
        }
        for ex in EXAMPLES
    ]
    metadata = [{"query_style": ex["style"]} for ex in EXAMPLES]

    client.create_examples(
        inputs=inputs, outputs=outputs, metadata=metadata, dataset_id=dataset.id
    )
    logger.info(f"Seeded {len(EXAMPLES)} examples for '{dataset_name}'.")


def seed_datasets(*, force: bool = False) -> None:
    job_ids = asyncio.run(seed_golden_jobs())
    client = Client(api_key=settings.langsmith_api_key)
    seed_matching_dataset(client, job_ids, force=force)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed golden jobs + LangSmith eval datasets"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete and recreate the matching dataset if it already exists",
    )
    args = parser.parse_args()
    seed_datasets(force=args.force)
