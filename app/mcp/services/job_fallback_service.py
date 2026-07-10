"""Fallback orchestration service — DB → JDL API → upsert → re-query.

Three-step pattern:
  1. Query DB
  2. If hits < threshold: fetch from JDL API, normalize, upsert, re-query DB
  3. Return DB-sourced results (never raw API data)

In-flight dedup prevents duplicate API calls for identical concurrent queries.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from uuid import UUID

import httpx

from app.core.config.settings import Settings
from app.core.jdl.client import JobDataLakeClient
from app.core.jdl.normalization import normalize_job
from app.mcp.mcp_schemas import JobDetailOutput, JobHit, SearchJobsOutput
from app.mcp.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)

# Module-level in-flight dedup map: query_key -> asyncio.Future
_in_flight: dict[str, asyncio.Future] = {}
_dedup_lock = asyncio.Lock()


class JobFallbackService:
    """Orchestrates the three-step fallback: DB → API → upsert → re-query."""

    def __init__(
        self,
        job_repo: JobRepository,
        jdl_client: JobDataLakeClient | None,
        settings: Settings,
    ) -> None:
        self.job_repo = job_repo
        self.jdl_client = jdl_client
        self.settings = settings
        self._fallback_enabled = settings.fallback_enabled and jdl_client is not None
        if not self._fallback_enabled:
            logger.warning(
                "JDL fallback disabled: no JDL client or fallback disabled in settings"
            )

    async def search_with_fallback(
        self,
        query: str,
        limit: int,
        threshold: int,
        criteria: dict,
    ) -> SearchJobsOutput:
        """Three-step fallback search.

        1. Query DB first
        2. If hits < threshold: fetch from JDL, upsert, re-query DB
        3. Return results (always from DB, never raw API)
        """
        # Step 1: Query DB
        db_results = await self.job_repo.search(
            query=query, limit=limit, cosine_threshold=0.5
        )

        # Check if fallback is needed (strict less-than)
        if not self._fallback_enabled or len(db_results) >= threshold:
            hits = self._hits_from_raw(db_results)
            return SearchJobsOutput(hits=hits, total=len(hits))

        # Step 2: Fallback to JDL API
        query_key = hashlib.sha256(query.lower().strip().encode()).hexdigest()
        dropped_count = 0
        fallback_start = time.monotonic()

        # In-flight dedup: use shared future
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        async with _dedup_lock:
            if query_key in _in_flight:
                logger.info("awaiting in-flight fallback for query=%s", query)
                return await _in_flight[query_key]
            _in_flight[query_key] = future

        try:
            try:
                # Fetch from JDL API with a timeout to prevent hanging
                try:
                    api_jobs = await asyncio.wait_for(
                        self.jdl_client.search_jobs(**criteria),
                        timeout=30.0,
                    )
                except TimeoutError:
                    logger.warning("JDL fallback timed out for query=%s", query)
                    hits = self._hits_from_raw(db_results)
                    result = SearchJobsOutput(hits=hits, total=len(hits))
                    if not future.done():
                        future.set_result(result)
                    return result

                if not isinstance(api_jobs, list):
                    api_jobs = api_jobs.get("jobs", []) if api_jobs else []

                if not api_jobs:
                    hits = self._hits_from_raw(db_results)
                    result = SearchJobsOutput(hits=hits, total=len(hits))
                    if not future.done():
                        future.set_result(result)
                    return result

                # Cap results
                api_jobs = api_jobs[: self.settings.fallback_max_results]

                # Normalize — drop malformed entries
                valid_jobs = []
                for raw in api_jobs:
                    try:
                        normalized = normalize_job(raw, source_name="jobdatalake")
                        valid_jobs.append(normalized)
                    except (ValueError, KeyError) as exc:
                        dropped_count += 1
                        logger.warning("fallback dropped malformed job: %s", exc)

                if valid_jobs:
                    upserted = await self.job_repo.upsert_from_fallback(valid_jobs)
                    if upserted:
                        self._schedule_embeddings(upserted)

            finally:
                _in_flight.pop(query_key, None)

            # Step 3: Re-query DB (now populated with fallback results)
            final = await self.job_repo.search(
                query=query, limit=limit, cosine_threshold=0.5
            )
            hits = self._hits_from_raw(final)
            fallback_elapsed = time.monotonic() - fallback_start
            logger.info(
                "fallback completed query=%s api_results=%d db_hits=%d "
                "dropped=%d latency=%.2fs",
                query,
                len(api_jobs),
                len(hits),
                dropped_count,
                fallback_elapsed,
            )
            result = SearchJobsOutput(
                hits=hits,
                total=len(hits),
                fallback_used=True,
                dropped_count=dropped_count,
            )
            if not future.done():
                future.set_result(result)
            return result

        except httpx.HTTPError as exc:
            logger.warning("JDL fallback failed: query=%s error=%s", query, exc)
            hits = self._hits_from_raw(db_results)
            result = SearchJobsOutput(hits=hits, total=len(hits))
            if not future.done():
                future.set_result(result)
            return result

    async def get_job_with_fallback(self, job_id: UUID) -> JobDetailOutput | None:
        """Look up a single job by ID, falling back to JDL API if not in DB.

        1. Check local DB first (by UUID)
        2. If not found, check by source_job_id (e.g. JDL external ID)
        3. If still not found, fetch from JDL API, upsert, return
        """
        # Step 1: Check local DB by UUID
        job = await self.job_repo.get_by_id(job_id)
        if job is not None:
            return JobDetailOutput.from_job(job)

        # Step 2: Check by source_job_id (for JDL external IDs passed as UUIDs)
        job = await self.job_repo.get_by_source_job_id(str(job_id))
        if job is not None:
            return JobDetailOutput.from_job(job)

        # Step 3: Fallback to JDL API (if enabled)
        if not self._fallback_enabled:
            return None

        try:
            raw = await asyncio.wait_for(
                self.jdl_client.get_job_by_id(str(job_id)),
                timeout=15.0,
            )
            if raw is None:
                return None  # 404 from JDL

            normalized = normalize_job(raw, source_name="jobdatalake")
            upserted = await self.job_repo.upsert_from_fallback([normalized])

            if upserted:
                self._schedule_embeddings(upserted)
                return JobDetailOutput.from_job(upserted[0])

            return None

        except TimeoutError:
            logger.warning("JDL fallback timed out for job_id=%s", job_id)
            return None
        except httpx.HTTPError as exc:
            logger.warning("JDL fallback failed for job_id=%s: %s", job_id, exc)
            return None

    def _hits_from_raw(self, raw_results) -> list[JobHit]:
        """Convert raw search results to JobHit list."""
        if not raw_results:
            return []
        return [
            JobHit.from_job(h, score=getattr(h, "rrf_score", 0.0)) for h in raw_results
        ]

    def _schedule_embeddings(self, jobs: list) -> None:
        """Fire-and-forget embedding generation for upserted jobs."""
        asyncio.create_task(
            self._generate_embeddings_background(jobs),
            name=f"fallback-embeddings-{id(jobs)}",
        )

    async def _generate_embeddings_background(self, jobs: list) -> None:
        """Generate embeddings for fallback-upserted jobs (background task)."""
        try:
            from app.core.llm.embeddings import generate_job_embeddings

            for job in jobs:
                await generate_job_embeddings(job)
            logger.info("fallback embeddings generated for %d jobs", len(jobs))
        except Exception as exc:
            logger.error("fallback embedding generation failed: %s", exc)
