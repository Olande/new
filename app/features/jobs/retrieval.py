from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.jobs.models import Job
from app.features.jobs.schemas import JobCandidate


async def hybrid_search(
    session: AsyncSession,
    query_embedding: list[float],
    query_text: str,
    k: int = 10,
    candidate_pool: int = 40,
    semantic_weight: float = 0.7,
    lexical_weight: float = 0.3,
    trigram_weight: float = 0.0,
) -> list[JobCandidate]:
    """
    Perform multi-stage hybrid search using weighted Reciprocal Rank Fusion (RRF).
    """
    clean_query = query_text.strip() if query_text else ""
    stmt = text(
        "SELECT * FROM hybrid_search_jobs("
        ":query_embedding, :query_text, :k, :candidate_pool, "
        ":semantic_weight, :lexical_weight, :trigram_weight);"
    )
    result = await session.execute(
        stmt,
        {
            "query_embedding": str(query_embedding),
            "query_text": clean_query,
            "k": k,
            "candidate_pool": candidate_pool,
            "semantic_weight": semantic_weight,
            "lexical_weight": lexical_weight,
            "trigram_weight": trigram_weight,
        },
    )
    rows = result.all()
    if not rows:
        return []
    job_ids = [row.job_id for row in rows]
    scores_map = {row.job_id: row.rrf_score for row in rows}
    jobs_stmt = (
        select(Job).options(selectinload(Job.description)).where(Job.id.in_(job_ids))
    )
    jobs_result = await session.execute(jobs_stmt)
    jobs_map = {job.id: job for job in jobs_result.scalars().all()}
    return [
        JobCandidate(job=jobs_map[j_id], score=scores_map[j_id])
        for j_id in job_ids
        if j_id in jobs_map
    ]
