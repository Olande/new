from app.evaluation.constants import DEFAULT_SEARCH_PARAMS, SearchParams
from app.evaluation.search import run_search


async def retrieval_target(
    inputs: dict,
    params: SearchParams = DEFAULT_SEARCH_PARAMS,
) -> dict:
    """Run production hybrid search and return ranked jobs for evaluators."""
    query = inputs.get("query", "")
    ranked_jobs = await run_search(
        query_text=query,
        params=params,
        include_snippets=True,
    )
    return {
        "ranked_jobs": ranked_jobs,
        "ranked_job_ids": [j["id"] for j in ranked_jobs],
        "search_params": params.as_dict(),
    }
