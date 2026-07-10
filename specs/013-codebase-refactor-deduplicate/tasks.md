# Tasks: Codebase Refactoring — Deduplication & Simplification

**Input**: Design documents from `specs/013-codebase-refactor-deduplicate/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Format: `[ID] [Markers] [Story] Description`

- `[P]` — Can run in parallel (different files, no dependencies)
- `[TDD]` — RED-GREEN-REFACTOR: write failing test first
- `[REVIEW]` — Pause for human code review before proceeding
- `[SUBAGENT]` — Can be dispatched to a parallel subagent

## Commands

- **Run all tests**: `uv run pytest tests/ -v --tb=short 2>&1 | tail -30`
- **Run specific test**: `uv run pytest tests/test_fallback.py -v -k "pattern" --tb=short`
- **Graph tests**: `uv run pytest tests/test_graph.py -v --tb=short`
- **Lint**: `uv run ruff check app/ tests/`
- **Format**: `uv run ruff format app/ tests/`
- **Install deps**: `uv sync`

---

## Phase 1: Setup & Baseline

**Purpose**: Establish baseline metrics, verify clean starting state.

- [ ] **T001** [P] **Run baseline test suite**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

**Expected**: All tests pass. Record the exact test count and pass count.

- [ ] **T002** [P] **Run baseline lint check**

```bash
uv run ruff check app/ tests/ --no-cache
```

**Expected**: Zero warnings. Exit code 0.

- [ ] **T003** [P] **Record baseline LOC**

```bash
echo "=== App code ===" && find app -name "*.py" ! -path "*/migrations/*" -exec wc -l {} + | sort -rn && echo "=== Test code ===" && find tests -name "*.py" -exec wc -l {} + | sort -rn
```

**Expected**: Baseline captured for SC-001 verification.

- [ ] **T004** [P] **Record baseline large files**

```bash
echo "=== App files >250 lines ===" && find app -name "*.py" -exec wc -l {} + | awk '$1 > 250' | sort -rn && echo "=== Test files >400 lines ===" && find tests -name "*.py" -exec wc -l {} + | awk '$1 > 400' | sort -rn
```

**Expected**: Baseline captured for SC-002/SC-003 verification.

**Checkpoint**: Baseline established — proceed to Batch 1.

---

## Phase 2: Batch 1 — Shared Utilities (P1)

### Step 1.1 — Shared Retry Config

- [ ] **T005** [SUBAGENT] [US4] **Create `app/core/retry_config.py`**

Create the file at `app/core/retry_config.py`:

```python
from __future__ import annotations

import httpx
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter


class RetryConfig:
    """Centralized retry configuration for external API calls."""

    def __init__(
        self,
        max_attempts: int = 5,
        initial_wait: float = 1.0,
        max_wait: float = 60.0,
        retryable_exceptions: tuple[type[Exception], ...] = (
            httpx.HTTPStatusError,
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            ResourceExhausted,
            ServiceUnavailable,
        ),
    ) -> None:
        self.max_attempts = max_attempts
        self.initial_wait = initial_wait
        self.max_wait = max_wait
        self.retryable_exceptions = retryable_exceptions


# Presets matching each module's original config
API_RETRY = RetryConfig(max_attempts=5, initial_wait=2, max_wait=60)
EMBEDDING_RETRY = RetryConfig(max_attempts=5, initial_wait=1, max_wait=30)
SEARCH_RETRY = RetryConfig(max_attempts=6, initial_wait=3, max_wait=60)


def with_retry(config: RetryConfig | None = None, **overrides):
    """Return a tenacity decorator configured from RetryConfig."""
    cfg = config or API_RETRY
    return retry(
        retry=retry_if_exception_type(cfg.retryable_exceptions),
        stop=stop_after_attempt(cfg.max_attempts),
        wait=wait_exponential_jitter(initial=cfg.initial_wait, max=cfg.max_wait),
        reraise=True,
    )
```

- [ ] **T006** [US4] **Migrate `description.py` to shared retry config**

In `app/core/jdl/description.py`, replace the inline `@retry(...)` decorator (lines 28-39) with:

```python
from app.core.retry_config import API_RETRY, with_retry


@with_retry(API_RETRY)
async def fetch_jina_content(client: httpx.AsyncClient, source_url: str) -> str:
    ...
```

Remove unused tenacity imports. Run lint.

- [ ] **T007** [US4] **Migrate `company_summary.py` to shared retry config**

In `app/core/jdl/company_summary.py`, replace the inline `@retry(...)` decorator (lines 30-34) with:

```python
from app.core.retry_config import API_RETRY, with_retry


@with_retry(API_RETRY)
async def fetch_company_summary(tavily: TavilySearch, company_name: str) -> str | None:
    ...
```

Run lint.

- [ ] **T008** [US4] **Migrate `embeddings.py` to shared retry config**

In `app/core/llm/embeddings.py`, replace the nested `@retry(...)` in `embed_texts_in_batches` (lines 111-116) with:

```python
from app.core.retry_config import EMBEDDING_RETRY, with_retry


@with_retry(EMBEDDING_RETRY)
async def embed_one_batch(batch: tuple[str, ...]) -> list[list[float]]:
    ...
```

Run lint.

- [ ] **T009** [US4] **Migrate `search.py` to shared retry config**

In `app/evaluation/search.py`, replace the `@retry(...)` on `_embed_query` (lines 136-141) with:

```python
from app.core.retry_config import SEARCH_RETRY, with_retry


@with_retry(SEARCH_RETRY)
async def _embed_query(client: Any, query: str) -> list[float]:
    ...
```

Run lint.

- [ ] **T010** [US4] **Verify retry migration**

```bash
grep -rn "@retry" app/ | grep -v __pycache__ | grep -v retry_config.py
```

**Expected**: Only one `@retry` in `app/core/retry_config.py:with_retry`. All callers use the `@with_retry(...)` factory.

- [ ] **T011** [US4] **Run tests and commit**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
uv run ruff check app/ tests/
git add -A && git commit -m "feat: extract shared retry config into app/core/retry_config.py"
```

**Checkpoint**: Retry config centralized. All tests pass.

---

### Step 1.2 — Shared Batch Processor

- [ ] **T012** [SUBAGENT] [TDD] [US1] **Write tests for batch processor**

Create `tests/test_batch.py`:

```python
"""Tests for app/core/batch.py shared batch processor."""

import asyncio

import pytest

from app.core.batch import BatchProcessorConfig, process_in_batches


@pytest.mark.asyncio
async def test_process_in_batches_all_succeed():
    results = await process_in_batches(
        items=[1, 2, 3],
        processor=lambda x: asyncio.sleep(0.01) or (x * 2),
        config=BatchProcessorConfig(batch_size=2, max_concurrency=2),
    )
    assert results == [2, 4, 6]


@pytest.mark.asyncio
async def test_process_in_batches_one_fails():
    results = await process_in_batches(
        items=[1, 0, 3],
        processor=lambda x: 10 // x,
        config=BatchProcessorConfig(batch_size=2, return_exceptions=True),
    )
    assert results[0] == 10
    assert isinstance(results[1], ZeroDivisionError)
    assert results[2] == 3


@pytest.mark.asyncio
async def test_process_in_batches_all_fail():
    results = await process_in_batches(
        items=[0, 0],
        processor=lambda x: 10 // x,
        config=BatchProcessorConfig(batch_size=1, return_exceptions=True),
    )
    assert len(results) == 2
    assert all(isinstance(r, ZeroDivisionError) for r in results)


@pytest.mark.asyncio
async def test_process_in_batches_empty():
    results = await process_in_batches(
        items=[],
        processor=lambda x: x,
        config=BatchProcessorConfig(),
    )
    assert results == []
```

Run: `uv run pytest tests/test_batch.py -v --tb=short`
**Expected**: FAIL — `app.core.batch` not found.

- [ ] **T013** [TDD] [US1] **Create `app/core/batch.py`**

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from aiolimiter import AsyncLimiter


T = TypeVar("T")
U = TypeVar("U")


class BatchProcessorConfig:
    def __init__(
        self,
        batch_size: int = 10,
        max_concurrency: int = 3,
        return_exceptions: bool = True,
        rate_per_second: float | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.max_concurrency = max_concurrency
        self.return_exceptions = return_exceptions
        self.rate_per_second = rate_per_second


DEFAULT_BATCH_CONFIG = BatchProcessorConfig()


async def process_in_batches(
    items: Sequence[T],
    processor: Callable[[T], Awaitable[U]],
    config: BatchProcessorConfig = DEFAULT_BATCH_CONFIG,
) -> list[U | BaseException]:
    from itertools import batched

    semaphore = asyncio.Semaphore(config.max_concurrency)
    limiter = AsyncLimiter(config.rate_per_second, 1) if config.rate_per_second else None

    async def _run(item: T) -> U:
        async with semaphore:
            if limiter:
                async with limiter:
                    return await processor(item)
            return await processor(item)

    results: list[U | BaseException] = []
    for batch in batched(items, config.batch_size, strict=False):
        tasks = [asyncio.create_task(_run(item)) for item in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=config.return_exceptions)
        results.extend(batch_results)
    return results
```

- [ ] **T014** [TDD] [US1] **Verify batch processor tests pass**

```bash
uv run pytest tests/test_batch.py -v --tb=short
```

**Expected**: All 4 tests PASS.

- [ ] **T015** [SUBAGENT] [TDD] [US1] **Migrate `description.py` to batch processor**

In `app/core/jdl/description.py`, replace:

```python
from itertools import batched

semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
limiter = AsyncLimiter(REQUESTS_PER_SECOND, 1)
```

And replace lines 94-130 (the for-batched-gather loop in `populate_job_descriptions`) with:

```python
from app.core.batch import BatchProcessorConfig, process_in_batches

# In populate_job_descriptions:
batch_config = BatchProcessorConfig(
    batch_size=batch_size,
    max_concurrency=MAX_CONCURRENT_REQUESTS,
    rate_per_second=REQUESTS_PER_SECOND,
)
responses = await process_in_batches(
    items=list(rows),
    processor=lambda row: fetch_jina_content(client, row.source_url),
    config=batch_config,
)
for (job_id, source_url), response in zip(rows, responses, strict=False):
    if isinstance(response, Exception):
        logger.warning("Failed fetching job %s (%s): %s", job_id, source_url, response)
        continue
    descriptions.append(JobDescription(job_id=job_id, cleaned_text=response))
```

Remove unused `batched`, `semaphore`, `limiter` imports. Run lint.

- [ ] **T016** [US1] **Migrate `company_summary.py` to batch processor**

In `app/core/jdl/company_summary.py`, replace the duplicated for-batched-gather pattern in both `populate_company_summaries` (lines 98-127) and `populate_for_companies` (lines 188-218) with:

```python
from app.core.batch import BatchProcessorConfig, process_in_batches

batch_config = BatchProcessorConfig(batch_size=batch_size, max_concurrency=batch_size)
responses = await process_in_batches(
    items=list(company_batch),
    processor=lambda name: fetch_company_summary(tavily, name),
    config=batch_config,
)
```

Remove unused `batched` import. Run lint.

- [ ] **T017** [US1] **Verify batch migration and commit**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
uv run ruff check app/ tests/
git add -A && git commit -m "feat: extract shared batch processor into app/core/batch.py"
```

**Checkpoint**: Batch processor created and 2 callers migrated. Tests pass.

---

### Step 1.3 — Shared Pagination Utility

- [ ] **T018** [SUBAGENT] [TDD] [US6] **Write tests for pagination utility**

Create `tests/test_pagination.py`:

```python
import pytest

from app.core.pagination import PaginationParams, paginate_api


@pytest.mark.asyncio
async def test_paginate_single_page():
    async def fetch_page(page: int, per_page: int) -> dict:
        return {"jobs": [{"id": i} for i in range(3)], "found": 3}

    results = [item async for item in paginate_api(fetch_page, lambda d: d["jobs"])]
    assert results == [{"id": 0}, {"id": 1}, {"id": 2}]


@pytest.mark.asyncio
async def test_paginate_multi_page():
    call_count = 0

    async def fetch_page(page: int, per_page: int) -> dict:
        nonlocal call_count
        call_count += 1
        return {"jobs": [{"id": page * 10 + i} for i in range(per_page)], "found": 25}

    results = [item async for item in paginate_api(fetch_page, lambda d: d["jobs"], PaginationParams(per_page=10))]
    assert len(results) == 25
    assert call_count == 3


@pytest.mark.asyncio
async def test_paginate_empty():
    async def fetch_page(page: int, per_page: int) -> dict:
        return {"jobs": [], "found": 0}

    results = [item async for item in paginate_api(fetch_page, lambda d: d["jobs"])]
    assert results == []
```

Run: `uv run pytest tests/test_pagination.py -v --tb=short`
**Expected**: FAIL — module not found.

- [ ] **T019** [TDD] [US6] **Create `app/core/pagination.py`**

```python
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any, TypeVar


T = TypeVar("T")


class PaginationParams:
    def __init__(self, per_page: int = 50, max_results: int | None = None, page_cap: int = 50) -> None:
        self.per_page = per_page
        self.max_results = max_results
        self.page_cap = page_cap


DEFAULT_PAGINATION = PaginationParams()


async def paginate_api(
    fetch_page: Callable[[int, int], Any],
    extract_items: Callable[[dict], list[T]],
    config: PaginationParams = DEFAULT_PAGINATION,
) -> AsyncIterator[T]:
    page = 1
    yielded = 0

    while True:
        data = await fetch_page(page, config.per_page)
        items = extract_items(data) if isinstance(data, dict) else []
        if not items:
            break
        for item in items:
            yield item
            yielded += 1
            if config.max_results and yielded >= config.max_results:
                return
        if len(items) < config.per_page:
            break
        found = data.get("found", 0) if isinstance(data, dict) else 0
        if page * config.per_page >= found:
            break
        if page >= config.page_cap:
            break
        page += 1
```

- [ ] **T020** [TDD] [US6] **Verify pagination tests pass**

```bash
uv run pytest tests/test_pagination.py -v --tb=short
```

**Expected**: All 3 tests PASS.

- [ ] **T021** [US6] **Migrate `client.py:search_all_results()` to pagination utility**

In `app/core/jdl/client.py`, replace the manual pagination loop in `search_all_results` (lines 77-114) with:

```python
from app.core.pagination import PaginationParams, paginate_api


def search_all_results(
    self,
    criteria: JobSearchCriteria,
    max_results: int | None = None,
    per_page: int = 50,
    page_cap: int | None = None,
) -> AsyncIterator[dict]:
    page_cap = page_cap or settings.discovery_page_cap
    search_params = build_search_params(criteria)
    pagination = PaginationParams(per_page=per_page, max_results=max_results, page_cap=page_cap)

    async def _fetch_page(page: int, per_page: int) -> dict:
        return await self.search_jobs(per_page=per_page, page=page, **search_params)

    return paginate_api(_fetch_page, lambda d: d.get("jobs", []), pagination)
```

- [ ] **T022** [US6] **Verify pagination migration and commit**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
uv run ruff check app/ tests/
git add -A && git commit -m "feat: extract shared pagination utility into app/core/pagination.py"
```

**Checkpoint**: Pagination utility created and JDL client migrated. Tests pass.

---

### Step 1.4 — Central Field Mapping

- [ ] **T023** [SUBAGENT] [US2] **Add `to_hit()` and `to_detail()` methods to `JobHit`/`JobDetailOutput`**

In `app/mcp/mcp_schemas.py`, add factory methods that consume an ORM-like dict:

```python
class JobHit(BaseModel):
    id: str
    title: str
    company_name: str
    required_skills: list[str] = []
    remote_type: str | None = None
    locations: list[str] = []
    score: float
    fallback_source: str | None = None

    @classmethod
    def from_job(cls, job, score: float = 0.0) -> JobHit:
        return cls(
            id=str(job.id),
            title=job.title,
            company_name=job.company_name,
            required_skills=list(job.required_skills or []),
            remote_type=job.remote_type,
            locations=list(job.locations or []),
            score=score,
            fallback_source=getattr(job, "fallback_source", None),
        )


class JobDetailOutput(BaseModel):
    id: str
    title: str
    company_name: str
    description: str = ""
    required_skills: list[str] = []
    locations: list[str] = []
    remote_type: str | None = None
    employment_type: str | None = None
    seniority: list[str] = []
    fallback_source: str | None = None

    @classmethod
    def from_job(cls, job, description: str = "") -> JobDetailOutput:
        return cls(
            id=str(job.id),
            title=job.title,
            company_name=job.company_name,
            description=description,
            required_skills=list(job.required_skills or []),
            locations=list(job.locations or []),
            remote_type=job.remote_type,
            employment_type=job.employment_type,
            seniority=list(job.seniority or []),
            fallback_source=getattr(job, "fallback_source", None),
        )
```

- [ ] **T024** [US2] **Remove `_job_to_detail_output` in `job_fallback_service.py`**

Replace `_job_to_detail_output(self, job)` (lines 217-234) with:

```python
from app.mcp.mcp_schemas import JobDetailOutput

# In get_job_with_fallback, replace:
#   return self._job_to_detail_output(job)
# with:
#   return JobDetailOutput.from_job(job)
```

Remove the `_job_to_detail_output` method entirely.

- [ ] **T025** [US2] **Simplify `_hits_from_raw` in `job_fallback_service.py`**

Replace `_hits_from_raw(self, raw_results)` (lines 236-254) with:

```python
def _hits_from_raw(self, raw_results) -> list[JobHit]:
    if not raw_results:
        return []
    return [
        JobHit.from_job(h, score=getattr(h, "rrf_score", 0.0))
        for h in raw_results
    ]
```

- [ ] **T026** [US2] **Simplify `run_search` in `evaluation/search.py`**

In `app/evaluation/search.py`, replace the manual dict-building for `ranked` (lines 114-128) with `JobSearchResult` model (which already has a Pydantic schema). If `JobSearchResult` already has `model_dump()`, use that.

Keep `include_snippets` logic but remove duplicate field names. Run lint.

- [ ] **T027** [US2] **Verify field mapping equivalence**

```bash
uv run pytest tests/test_fallback.py -v -k "job_hit or search_jobs_output or job_detail" --tb=short
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
uv run ruff check app/ tests/
git add -A && git commit -m "feat: centralize Job field mappings via from_job() factory"
```

**Checkpoint**: 6 mapping locations → 2 (schema + factory). Tests pass.

---

### Step 1.5 — MCP Boilerplate Factory

- [ ] **T028** [SUBAGENT] [US2] **Create `app/mcp/factory.py`**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base import async_session


T = TypeVar("T")
U = TypeVar("U")


async def with_service(
    service_factory: Callable[[AsyncSession], T],
    action: Callable[[T], Awaitable[U]],
) -> U:
    """Manage DB session lifecycle and return the action result."""
    async with async_session() as session:
        service = service_factory(session)
        return await action(service)


async def with_user_service(
    service_factory: Callable[[AsyncSession], T],
    action: Callable[[T], Awaitable[U]],
    user_id: str,
) -> U:
    """Manage DB session lifecycle with pre-authenticated user."""
    async with async_session() as session:
        from app.mcp.di import set_request_context

        set_request_context(user_id=user_id, tenant_id=None)
        service = service_factory(session)
        return await action(service)
```

- [ ] **T029** [US2] **Refactor `mcp_server.py` tools to use factory**

Replace each tool's body from a pattern like:

```python
async with db_session_scope() as session:
    job_repo = JobRepository(session)
    fallback = _build_fallback_service(session)
    job_service = JobService(job_repo, fallback_service=fallback, settings=app_settings)
    res = await job_service.search_jobs(query=inp.query, limit=inp.limit, cosine_threshold=inp.cosine_threshold)
    return res.model_dump()
```

With:

```python
from app.mcp.factory import with_service

async def search_jobs_tool(query: str, limit: int = 10, cosine_threshold: float = 0.5) -> dict[str, Any]:
    inp = SearchJobsInput(query=query, limit=limit, cosine_threshold=cosine_threshold)
    return await with_service(
        lambda s: JobService(JobRepository(s), fallback_service=_build_fallback_service(s), settings=app_settings),
        lambda svc: svc.search_jobs(query=inp.query, limit=inp.limit, cosine_threshold=inp.cosine_threshold),
    )
```

Apply this pattern to `get_job_tool`, `get_my_profile_tool`, `create_application_draft_tool`, `submit_application_tool`, `confirm_submission_tool`.

For tools that need `require_user()`, use the pattern:

```python
user = require_user()
return await with_service(
    lambda s: SomeService(SomeRepo(s)),
    lambda svc: svc.some_method(user=user, ...),
)
```

Simplify `_build_fallback_service` to accept a session parameter only (it already takes `session`).

- [ ] **T030** [US2] **Verify MCP refactor and commit**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
uv run ruff check app/ tests/
git add -A && git commit -m "feat: reduce MCP tool boilerplate via app/mcp/factory.py"
```

**Checkpoint**: MCP boilerplate reduced. All tests pass.

---

### Step 1.6 — Simplify Skill Normalization & Dedup Hash

- [ ] **T031** [SUBAGENT] [US5] **Simplify `normalize_skills`**

In `app/core/jdl/normalization.py`, replace:

```python
def normalize_skills(skills: list[str] | None) -> list[str]:
    if not skills:
        return []
    seen: dict[str, str] = {}
    for skill in skills:
        stripped = skill.strip() if skill else ""
        if stripped:
            seen.setdefault(stripped.lower(), stripped)
    return list(seen.values())
```

With:

```python
from itertools import unique_everseen


def normalize_skills(skills: list[str] | None) -> list[str]:
    if not skills:
        return []
    stripped = [s.strip() for s in skills if s and s.strip()]
    return list(unique_everseen(stripped, key=str.lower))
```

Run lint.

- [ ] **T032** [US5] **Simplify `compute_dedup_hash` and `collapse_whitespace`**

In `app/core/jdl/normalization.py`, simplify `collapse_whitespace`:

```python
def collapse_whitespace(s: str) -> str:
    return " ".join(s.strip().lower().split()) if s else ""
```

This replaces the `re.sub(r"\s+", ...)` call with stdlib string operations.

Run lint.

- [ ] **T033** [US5] **Verify normalization still works and commit**

```bash
uv run pytest tests/test_fallback.py -v --tb=short 2>&1 | tail -10
uv run ruff check app/ tests/
git add -A && git commit -m "refactor: simplify normalize_skills and collapse_whitespace with stdlib"
```

**Checkpoint**: Reinvented wheel replaced. Tests pass.

---

### Step 1.7 — Simplify In-Flight Dedup

- [ ] **T034** [SUBAGENT] [US5] **Refactor in-flight dedup in `job_fallback_service.py`**

Replace the module-level `_in_flight: dict[str, asyncio.Event]` and `_dedup_lock` with:

```python
_in_flight: dict[str, asyncio.Future] = {}
```

Replace the lock/Event pattern in `search_with_fallback` (lines 80-103) with:

```python
# In-flight dedup: use shared future
loop = asyncio.get_running_loop()
future = loop.create_future()
async with _dedup_lock:
    if query_key in _in_flight:
        logger.info("awaiting in-flight fallback for query=%s", query)
        return await _in_flight[query_key]
    _in_flight[query_key] = future

try:
    # ... existing API fetch logic ...
    final = await self.job_repo.search(query=query, limit=limit, cosine_threshold=0.5)
    hits = self._hits_from_raw(final)
    result = SearchJobsOutput(hits=hits, total=len(hits), fallback_used=True)
    future.set_result(result)
    return result
except Exception as e:
    if not future.done():
        future.set_exception(e)
    raise
finally:
    _in_flight.pop(query_key, None)
```

**Note**: The waiter side uses `await _in_flight[query_key]` instead of `await _in_flight[query_key].wait()`.

- [ ] **T035** [US5] **Verify in-flight dedup refactor and commit**

```bash
uv run pytest tests/test_fallback.py -v -k "inflight or dedup" --tb=short
uv run pytest tests/ -v --tb=short 2>&1 | tail -10
uv run ruff check app/ tests/
git add -A && git commit -m "refactor: simplify in-flight dedup with asyncio.Future"
```

**Checkpoint**: Batch 1 complete. All 7 utility steps done. All tests pass.

---

## Phase 3: Batch 2 — Structural Changes (P2→P3)

### Step 2.1 — Split `nodes.py` into Focused Modules

- [ ] **T036** [US3] **Create `app/graph/query_nodes.py` — query analysis + memory + search**

Extract from `app/graph/nodes.py`:
- `load_career_memories_from_store` (lines 35-69)
- `migrate_career_memory_table_to_store` (lines 72-118)
- `analyze_query` (lines 121-135)
- `build_query_text` (lines 138-152)
- `hybrid_search` (lines 155-162)
- `route_to_scoring` (lines 165-171)
- `detect_submit_intent` (lines 289-291)
- `intent_router` (lines 294-297)

```python
"""Query analysis, memory, and search nodes."""

from __future__ import annotations

from typing import Any

from langgraph.graph import Send
from langgraph.types import Command

from app.core.config.settings import settings
from app.core.db.base import async_session
from app.core.jdl.schemas import JobSearchCriteria
from app.graph.graph_state import QAGraphState
from app.retrieval.hybrid_search import search_jobs


# ... copy all extracted functions here ...


def get_fast_model():
    from langchain.chat_models import init_chat_model
    return init_chat_model(model="gemini-2.5-flash", api_key=settings.gemini_api_key)
```

- [ ] **T037** [US3] **Create `app/graph/scoring_nodes.py` — scoring + critiquing**

Extract from `app/graph/nodes.py`:
- `score_candidate` (lines 174-182)
- `compile_results` (lines 185-194)
- `generate_draft` (lines 197-218)
- `find_ungrounded_claims` (lines 221-225)
- `heuristic_check` (lines 228-247)
- `llm_critic` (lines 250-286)

Also extract `get_frontier_model`:

```python
def get_frontier_model():
    from langchain.chat_models import init_chat_model
    return init_chat_model(model="gemini-3.1-flash-lite", api_key=settings.gemini_api_key)
```

- [ ] **T038** [US3] **Create `app/graph/submission_nodes.py` — application submission**

Extract:
- `prepare_submission` (lines 300-357)
- `request_human_approval` (lines 360-399)
- `execute_submission` (lines 402-454)

- [ ] **T039** [US3] **Update `agent.py` imports**

In `app/graph/agent.py`, replace:

```python
from app.graph.nodes import (...)
```

With:

```python
from app.graph.query_nodes import analyze_query, build_query_text, hybrid_search, intent_router, route_to_scoring, detect_submit_intent
from app.graph.scoring_nodes import score_candidate, compile_results, generate_draft, heuristic_check, llm_critic
from app.graph.submission_nodes import prepare_submission, request_human_approval, execute_submission
```

Remove `from app.graph.nodes import ...` line.

- [ ] **T040** [US3] **Remove `app/graph/nodes.py`**

```bash
rm app/graph/nodes.py
```

- [ ] **T041** [US3] **Verify graph tests pass after split**

```bash
uv run pytest tests/test_graph.py -v --tb=short
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
uv run ruff check app/ tests/
git add -A && git commit -m "refactor: split app/graph/nodes.py into query/scoring/submission modules"
```

**Checkpoint**: 454-line file eliminated. Graph agent still works. Tests pass.

---

### Step 2.2 — Extract Eval Data from Logic

- [ ] **T042** [SUBAGENT] [US6] **Create `scripts/eval_data.py` with extracted data**

Extract from `scripts/seed_eval_datasets.py`:
- `GOLDEN_JOBS` list (lines 12-62)
- `GOLDEN_JOB_IDS` dict (lines 64-66)
- `EXAMPLES` list (lines 111-216)
- Also export `_dedup_hash` helper

```python
"""Eval datasets: golden jobs and query examples for retrieval evaluation."""

import hashlib
import uuid

GOLDEN_JOBS = [
    {
        "key": "backend_fastapi_senior_remote",
        "title": "Senior Backend Engineer",
        "company_name": "Golden Eval Co",
        "required_skills": ["Python", "PostgreSQL", "FastAPI"],
        "description": "Senior backend engineer, Python and PostgreSQL, FastAPI, remote friendly.",
    },
    # ... copy all 7 golden jobs ...
]

GOLDEN_JOB_IDS = {
    job["key"]: uuid.uuid5(uuid.NAMESPACE_DNS, job["key"]) for job in GOLDEN_JOBS
}

EXAMPLES = [
    # ... copy all 20 examples ...
]


def dedup_hash(job_id: uuid.UUID) -> str:
    return hashlib.sha256(str(job_id).encode()).hexdigest()
```

- [ ] **T043** [US6] **Update `seed_eval_datasets.py` to import from data module**

Replace the inline data definitions at the top of `scripts/seed_eval_datasets.py` with:

```python
from scripts.eval_data import EXAMPLES, GOLDEN_JOB_IDS, GOLDEN_JOBS, dedup_hash as _dedup_hash
```

Remove the inline data lists (GOLDEN_JOBS, GOLDEN_JOB_IDS, EXAMPLES, _dedup_hash function).

- [ ] **T044** [US6] **Verify seed script still works and commit**

```bash
uv run ruff check scripts/ app/
python -c "from scripts.eval_data import GOLDEN_JOBS, EXAMPLES; print(f'{len(GOLDEN_JOBS)} jobs, {len(EXAMPLES)} examples')"
git add -A && git commit -m "refactor: extract eval data from seed_eval_datasets.py into scripts/eval_data.py"
```

**Checkpoint**: Data separated from logic. Script shrinks by ~60%.

---

### Step 2.3 — Split Large Test Files

- [ ] **T045** [SUBAGENT] [US7] **Extract shared fixtures to `tests/conftest.py`**

Create `tests/conftest.py` with fixtures from `tests/test_fallback.py`:

```python
"""Shared test fixtures for fallback-related tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config.settings import Settings


@pytest.fixture
def mock_settings():
    s = MagicMock(spec=Settings)
    s.fallback_enabled = True
    s.fallback_min_result_threshold = 5
    s.fallback_max_results = 20
    return s


@pytest.fixture
def job_repo():
    return MagicMock()


@pytest.fixture
def mock_jdl_client():
    return MagicMock()


@pytest.fixture
def fallback_service(job_repo, mock_jdl_client, mock_settings):
    from app.mcp.services.job_fallback_service import JobFallbackService
    return JobFallbackService(
        job_repo=job_repo,
        jdl_client=mock_jdl_client,
        settings=mock_settings,
    )


@pytest.fixture
def fallback_service_disabled(job_repo, mock_jdl_client, mock_settings):
    from app.mcp.services.job_fallback_service import JobFallbackService
    mock_settings.fallback_enabled = False
    return JobFallbackService(
        job_repo=job_repo,
        jdl_client=mock_jdl_client,
        settings=mock_settings,
    )
```

- [ ] **T046** [SUBAGENT] [US7] **Create `tests/test_jdl_client.py` — JDL client tests**

Extract from `tests/test_fallback.py` all tests for `JobDataLakeClient` (T013 tests, lines 212-258):

```python
"""Tests for app.core.jdl.client.JobDataLakeClient."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_job_by_id_found():
    from app.core.jdl.client import JobDataLakeClient
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "jdl_001", "title": "Engineer"}
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    client = JobDataLakeClient(api_key="test-key")
    client.client = mock_client
    client.limiter = MagicMock()
    client.limiter.__aenter__ = AsyncMock(return_value=None)
    client.limiter.__aexit__ = AsyncMock(return_value=None)
    result = await client.get_job_by_id("jdl_001")
    assert result == {"id": "jdl_001", "title": "Engineer"}
    mock_client.get.assert_called_once_with("https://api.jobdatalake.com/v1/jobs/jdl_001")


@pytest.mark.asyncio
async def test_get_job_by_id_not_found():
    from app.core.jdl.client import JobDataLakeClient
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    client = JobDataLakeClient(api_key="test-key")
    client.client = mock_client
    client.limiter = MagicMock()
    client.limiter.__aenter__ = AsyncMock(return_value=None)
    client.limiter.__aexit__ = AsyncMock(return_value=None)
    result = await client.get_job_by_id("nonexistent")
    assert result is None
```

- [ ] **T047** [SUBAGENT] [US7] **Create `tests/test_job_repo.py` — repository tests**

Extract repository tests from `tests/test_fallback.py` (T011, T012 — lines 160-206):

```python
"""Tests for app.mcp.repositories.job_repo.JobRepository."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_by_source_job_id_found():
    from app.mcp.repositories.job_repo import JobRepository
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_job = MagicMock()
    mock_job.title = "Sample Job"
    mock_result.scalar_one_or_none.return_value = mock_job
    mock_session.execute = AsyncMock(return_value=mock_result)
    repo = JobRepository(session=mock_session)
    job = await repo.get_by_source_job_id("jdl_source_001")
    assert job is not None
    assert job.title == "Sample Job"


@pytest.mark.asyncio
async def test_get_by_source_job_id_not_found():
    from app.mcp.repositories.job_repo import JobRepository
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    repo = JobRepository(session=mock_session)
    job = await repo.get_by_source_job_id("nonexistent")
    assert job is None


@pytest.mark.asyncio
async def test_upsert_from_fallback_empty():
    from app.mcp.repositories.job_repo import JobRepository
    repo = JobRepository(session=MagicMock())
    result = await repo.upsert_from_fallback([])
    assert result == []
```

- [ ] **T048** [SUBAGENT] [US7] **Create `tests/test_fallback_service.py` — service tests**

Extract service-level tests from `tests/test_fallback.py` (T014-T036, lines 266-812 excluding already-extracted tests):

This is the largest extraction. Include:
- `test_job_fallback_service_instantiation` (lines 266-276)
- `test_empty_db_triggers_fallback` (lines 331-419)
- `test_populated_db_no_fallback` (lines 422-445)
- `test_threshold_strict_lt` (lines 448-494)
- `test_api_error_graceful` (lines 497-516)
- `test_fallback_disabled` (lines 519-529)
- `test_malformed_job_dropped` (lines 532-613)
- `test_get_job_fallback` (lines 620-677)
- `test_get_job_in_db_no_api` (lines 679-701)
- `test_get_job_not_found_anywhere` (lines 703-714)
- `test_inflight_dedup` (lines 722-795)
- `test_jdl_client_init_failure_disables_fallback` (lines 803-812)

Import fixtures from `conftest`:

```python
"""Tests for app.mcp.services.job_fallback_service.JobFallbackService."""

from unittest.mock import AsyncMock, MagicMock

import pytest


# Test body uses conftest fixtures: mock_settings, job_repo, mock_jdl_client,
# fallback_service, fallback_service_disabled
```

- [ ] **T049** [US7] **Remove `tests/test_fallback.py`**

```bash
rm tests/test_fallback.py
```

- [ ] **T050** [US7] **Verify all tests pass with new file structure**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
uv run ruff check tests/
```

**Expected**: All previous tests still pass (same count, same test names).

- [ ] **T051** [US7] **Verify file size limits**

```bash
find tests -name "*.py" -exec wc -l {} + | awk '$1 > 400' | sort -rn
```

**Expected**: No output — all test files under 400 lines.

- [ ] **T052** [US7] **Commit test file split**

```bash
git add -A && git commit -m "refactor: split tests/test_fallback.py into per-module test files"
```

**Checkpoint**: Batch 2 complete. All test files < 400 lines.

---

## Phase 4: Final Validation

- [ ] **T053** [P] **Run full test suite**

```bash
uv run pytest tests/ -v --tb=short 2>&1
```

**Expected**: Zero failures. Compare test count against T001 baseline.

- [ ] **T054** [P] **Run lint & format**

```bash
uv run ruff check app/ tests/ && uv run ruff format app/ tests/ --check
```

**Expected**: Zero warnings. Exit code 0.

- [ ] **T055** [P] **Verify LOC reduction (SC-001)**

```bash
echo "=== App code ===" && find app -name "*.py" ! -path "*/migrations/*" -exec wc -l {} + | tail -1 && echo "=== Test code ===" && find tests -name "*.py" -exec wc -l {} + | tail -1
```

Compare against T003 baseline. **Expected**: At least 15% reduction in production code.

- [ ] **T056** [P] **Verify max file sizes (SC-002, SC-003)**

```bash
echo "=== App files >250 ===" && find app -name "*.py" -exec wc -l {} + | awk '$1 > 250' | sort -rn && echo "=== Test files >400 ===" && find tests -name "*.py" -exec wc -l {} + | awk '$1 > 400' | sort -rn
```

**Expected**: No output.

- [ ] **T057** [P] **Verify SC-004, SC-005, SC-006**

```bash
echo "=== Retry config locations ===" && grep -rn "@retry" app/ | grep -v __pycache__ | grep -v retry_config.py
echo "=== Batch pattern locations ===" && grep -rn "batched.*gather\|asyncio\.gather.*return_exceptions" app/ --include="*.py"
```

**Expected**: No output for either command.

- [ ] **T058** **Commit final validation**

```bash
git add -A && git commit -m "chore: final validation — all tests pass, lint clean, LOC reduced"
```

---

## Dependencies & Execution Order

### Within Batch 1

```
T005-T011 (retry config) ──┬── T012-T017 (batch processor) ── T018-T022 (pagination)
                           │
                           └── T023-T027 (field mapping) ── T028-T030 (MCP factory)
                                                          ── T031-T035 (simplify patterns)
```

T005-T011, T012-T017, T018-T022, T023-T027, T028-T030, T031-T035 are **sequential within themselves** but can be run in any order relative to other step groups. Steps 1.6 and 1.7 have no dependencies on other steps.

### Within Batch 2

T036-T041 (split nodes) → T042-T044 (extract data) → T045-T052 (split tests)

Batch 2 is sequential — each sub-step depends on the previous one being clean.

### Parallel Opportunities

| Group | Tasks | Reason |
|-------|-------|--------|
| **Setup** | T001-T004 | Baseline — no dependencies |
| **Retry config** | T005-T011 | Sequential within group |
| **Batch processor** | T012-T017 | Sequential within group |
| **Pagination** | T018-T022 | Sequential within group |
| **Field mapping** | T023-T027 | Sequential within group |
| **MCP factory** | T028-T030 | Sequential within group |
| **Simplify patterns** | T031-T035 | Sequential within group |
| **Split nodes** | T036-T041 | Sequential |
| **Extract data** | T042-T044 | Sequential |
| **Split tests** | T045-T052 | Sequential |
| **Final validation** | T053-T058 | All parallel |

All 6 Batch 1 step groups can be dispatched as `[SUBAGENT]` tasks in parallel — they touch different files and have no cross-dependencies. Steps within a group are sequential.

### Checkpoint Gates

1. **After T011**: Retry config centralized. Run `uv run pytest tests/`.
2. **After T017**: Batch processor done. Run `uv run pytest tests/`.
3. **After T022**: Pagination utility done. Run `uv run pytest tests/`.
4. **After T027**: Field mapping centralized. Run `uv run pytest tests/`.
5. **After T030**: MCP factory done. Run `uv run pytest tests/`.
6. **After T041**: `nodes.py` split. Run `uv run pytest tests/test_graph.py`.
7. **After T044**: Eval data extracted. Run seed script.
8. **After T052**: Test files split. Run `uv run pytest tests/`.
9. **Final**: T053-T058 — full validation suite.
