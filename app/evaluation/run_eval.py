import asyncio
import os
import sys
from loguru import logger
from langsmith import aevaluate, Client
from app.evaluation.evaluators import (
    ndcg_at_10,
    mrr,
    rubric_evaluator,
    hallucination_evaluator,
)


# Targets for evaluation
async def retrieval_target(inputs: dict) -> dict:
    from app.db.base import async_session
    from app.retrieval.search import hybrid_search
    from app.retrieval.embeddings import get_embeddings_client

    query = inputs.get("query", "")

    # We do a minimal wrapper because hybrid search requires DB session
    async with async_session() as session:
        embeddings = get_embeddings_client()
        query_embedding = await embeddings.aembed_query(query)
        candidates = await hybrid_search(
            session, query_embedding=query_embedding, query_text=query, k=10
        )

    ranked_ids = [str(c.job.id) for c in candidates]
    return {"ranked_job_ids": ranked_ids}


async def generation_target(inputs: dict) -> dict:
    from app.agents.resume_agent import generate_resume_draft

    draft = await generate_resume_draft(
        career_memory=inputs.get("career_memory", []),
        job_title=inputs.get("job_title", ""),
        company_name=inputs.get("company_name", ""),
        required_skills=inputs.get("required_skills", []),
        job_description=inputs.get("job_description", ""),
        critique=inputs.get("critique"),
    )

    return {"resume_draft": draft}


async def run_evaluations():
    if not os.getenv("LANGSMITH_API_KEY"):
        logger.error("LANGSMITH_API_KEY not set. Cannot run evaluations.")
        sys.exit(1)

    client = Client()

    logger.info("Running retrieval evaluation...")
    retrieval_results = await aevaluate(
        retrieval_target,
        data="careerpilot-matching-eval",
        evaluators=[ndcg_at_10, mrr],
        experiment_prefix="hybrid-retrieval",
    )

    logger.info("Running generation evaluation...")
    await aevaluate(
        generation_target,
        data="careerpilot-generation-eval",
        evaluators=[rubric_evaluator, hallucination_evaluator],
        experiment_prefix="resume-generation",
        max_concurrency=5,
    )

    # Compare with previous experiment runs to check for regression
    NDCG_REGRESSION_THRESHOLD = 0.05
    has_error = False

    try:
        # Fetch current project metrics
        retrieval_project = client.read_project(
            project_name=retrieval_results.experiment_name
        )

        # Get prior runs for the dataset
        datasets = list(client.list_datasets(dataset_name="careerpilot-matching-eval"))
        if datasets:
            dataset_id = datasets[0].id
            prior_projects = list(
                client.list_projects(
                    reference_dataset_id=dataset_id,
                )
            )

            # Sort projects by start_time to find the latest completed run prior to the current one
            completed_projects = [
                p for p in prior_projects if p.id != retrieval_project.id
            ]
            completed_projects.sort(
                key=lambda p: p.start_time or p.created_at, reverse=True
            )

            if completed_projects:
                latest_prior = completed_projects[0]

                # Fetch stats using client API (simplified for demonstration, typically you might aggregate runs
                # but project read usually has basic stats)
                # We need to fetch feedback stats
                runs = list(
                    client.list_runs(project_id=retrieval_project.id, execution_order=1)
                )
                prior_runs = list(
                    client.list_runs(project_id=latest_prior.id, execution_order=1)
                )

                def avg_metric(runs_list, metric_name):
                    scores = []
                    for r in runs_list:
                        for f in r.feedback_stats or {}:
                            if f == metric_name:
                                scores.append(r.feedback_stats[f].get("avg", 0.0))
                    if not scores:
                        return 0.0
                    return sum(scores) / len(scores)

                current_ndcg = avg_metric(runs, "ndcg_at_10")
                prior_ndcg = avg_metric(prior_runs, "ndcg_at_10")

                logger.info(
                    f"Current NDCG@10: {current_ndcg:.4f}, Prior NDCG@10: {prior_ndcg:.4f}"
                )

                if prior_ndcg > 0:
                    relative_drop = (prior_ndcg - current_ndcg) / prior_ndcg
                    if relative_drop > NDCG_REGRESSION_THRESHOLD:
                        logger.error(
                            f"Regression detected! NDCG@10 dropped by {relative_drop * 100:.1f}% (> {NDCG_REGRESSION_THRESHOLD * 100:.1f}%)"
                        )
                        has_error = True
            else:
                logger.info("No prior complete experiment to compare against.")
    except Exception as e:
        logger.warning(f"Error comparing retrieval metrics: {e}")

    logger.info("Evaluations completed.")
    if has_error:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_evaluations())
