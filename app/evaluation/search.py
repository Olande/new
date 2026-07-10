import textwrap
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.db.base import async_session
from app.core.db.models.job import JobDescription
from app.core.jdl.schemas import JobSearchResult
from app.core.llm.embeddings import get_embeddings_client
from app.retrieval.hybrid_search import search_jobs

# LangSmith dataset produced by scripts/seed_eval_datasets.py
RETRIEVAL_DATASET = "careerpilot-matching-eval-v2"

# Query styles stored in example metadata by the seeder
MATCHING_STYLES = frozenset({"exact_terms", "paraphrase", "distractor"})
NO_MATCH_STYLE = "no_match"


@dataclass(frozen=True, slots=True)
class SearchParams:
    """Hybrid search knobs used for both production defaults and eval sweeps."""

    bm25_weight: float = 0.1
    vector_weight: float = 0.9
    cosine_distance_threshold: float = 0.5
    result_limit: int = 20

    def as_dict(self) -> dict:
        return asdict(self)


# Align with app.retrieval.hybrid_search.search_jobs defaults
DEFAULT_SEARCH_PARAMS = SearchParams()


async def search_jobs_with_embedding(
    db: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    params: SearchParams = DEFAULT_SEARCH_PARAMS,
) -> list[Any]:
    """Call hybrid_search_jobs with a precomputed embedding (avoids re-embed in grids)."""
    stmt = text("""
        SELECT * FROM hybrid_search_jobs(
            :query_text, :query_embedding, :cosine_distance_threshold,
            :bm25_weight, :vector_weight, :result_limit
        )
    """)
    result = await db.execute(
        stmt,
        {
            "query_text": query_text,
            "query_embedding": str(query_embedding),
            "cosine_distance_threshold": params.cosine_distance_threshold,
            "bm25_weight": params.bm25_weight,
            "vector_weight": params.vector_weight,
            "result_limit": params.result_limit,
        },
    )
    return result.mappings().all()


async def run_search(
    query_text: str,
    params: SearchParams = DEFAULT_SEARCH_PARAMS,
    *,
    query_embedding: list[float] | None = None,
    include_snippets: bool = False,
) -> list[dict[str, Any]]:
    """
    Execute hybrid search and return serializable ranked hits.

    When ``query_embedding`` is provided, skips the embed API call.
    """
    async with async_session() as session:
        if query_embedding is not None:
            rows = await search_jobs_with_embedding(
                session, query_text, query_embedding, params
            )
            candidates = [JobSearchResult.model_validate(dict(row)) for row in rows]
        else:
            candidates = await search_jobs(
                session,
                query_text=query_text,
                cosine_distance_threshold=params.cosine_distance_threshold,
                bm25_weight=params.bm25_weight,
                vector_weight=params.vector_weight,
                result_limit=params.result_limit,
            )

        descriptions: dict = {}
        if include_snippets and candidates:
            job_ids = [c.id for c in candidates]
            stmt = select(JobDescription).where(JobDescription.job_id.in_(job_ids))
            result = await session.execute(stmt)
            descriptions = {desc.job_id: desc.cleaned_text for desc in result.scalars()}

    ranked: list[dict[str, Any]] = []
    for c in candidates:
        item: dict[str, Any] = {
            "id": str(c.id),
            "title": c.title,
            "company_name": c.company_name,
            "required_skills": list(c.required_skills) if c.required_skills else [],
            "score": float(c.rrf_score),
        }
        if include_snippets:
            desc = descriptions.get(c.id, "") or ""
            item["description_snippet"] = (
                textwrap.shorten(desc, width=500, placeholder="...") if desc else ""
            )
        ranked.append(item)
    return ranked


def _is_rate_limited(exc: BaseException) -> bool:
    return "429" in str(exc)


@retry(
    retry=retry_if_exception(_is_rate_limited),
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=3, max=60),
    reraise=True,
)
async def _embed_query(client: Any, query: str) -> list[float]:
    return await client.aembed_query(query)


async def precompute_query_embeddings(queries: list[str]) -> dict[str, list[float]]:
    """Embed unique query strings once (for grid search / multi-param runs)."""
    client = get_embeddings_client()
    unique = list(dict.fromkeys(queries))
    embeddings: dict[str, list[float]] = {}
    for q in unique:
        embeddings[q] = await _embed_query(client, q)
    return embeddings


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
