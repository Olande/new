# Implementation Plan: JDL Client (Job Data Lake Integration)

**Branch**: `phase4-infra-decoupling` | **Status**: Migrated | **Spec**: `specs/007-jdl-client/spec.md`

**Note**: This plan was reverse-engineered from the existing implementation.

## Summary

Integrate with the Job Data Lake API to discover, normalize, enrich, and persist job postings. A background daemon runs ingestion cycles every 12 hours, crawling seed search criteria, normalizing raw API output, deduplicating by hash, enriching with company summaries (Tavily) and full descriptions (Jina AI), and closing stale jobs.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: `httpx` (HTTP client), `httpx-retries` (retry transport), `aiolimiter` (rate limiting), `tenacity` (retry decorator), `langchain-tavily` (company search), dateutil (date parsing)
**Storage**: PostgreSQL via SQLAlchemy async (`Job`, `JobSource`, `JobDescription` models)
**Testing**: ❌ No dedicated tests exist
**Target Platform**: Linux (Docker container — daemon runs as separate container `jdl-daemon`)
**Project Type**: Background data ingestion daemon + data access layer

## Module Map

```
app/core/jdl/
├── client.py           ← Async HTTP client, rate-limited, retry transport
├── schemas.py          ← Pydantic models: search criteria, job read/create, embedding doc
├── normalization.py    ← Input cleaning, skill dedup, SHA-256 dedup hash
├── repository.py       ← DB upsert, stale job detection, paginated listing
├── discovery.py        ← Orchestrator: crawl → normalize → upsert → embeddings → enrich
├── company_summary.py  ← Tavily-powered company enrichment (batched, retried)
├── description.py      ← Jina AI-powered job description fetching (rate-limited)
└── seed_criteria.py    ← Default 7 seed search queries

app/scripts/
└── jdl_daemon.py       ← 12-hour daemon loop

app/core/db/models/
└── job.py              ← Job, JobSource, JobDescription SQLAlchemy models
```

## Key Design Decisions

1. **Dedup by hash**: SHA-256 of normalized `company_name|title|skills` — simple, deterministic, no DB query needed before upsert
2. **Postgres upsert**: Uses `ON CONFLICT DO UPDATE` on `dedup_hash` — atomic, avoids race conditions
3. **Stale job closing**: Incremental `unconfirmed_count` counter per `JobSource` — a job closes only when ALL its sources exceed the threshold
4. **Company summary backfill**: Before calling Tavily, existing summaries are copied to same-company rows (free dedup)
5. **Rate limiting at multiple levels**: `aiolimiter` for JDL client, `asyncio.Semaphore` + `AsyncLimiter` for Jina AI, `tenacity` for retry

## Dependency Flow

```
jdl_daemon.py
  └── run_discovery() [discovery.py]
        ├── JobDataLakeClient [client.py] → JDL API
        ├── normalize_job() [normalization.py]
        ├── upsert_job() / upsert_job_source() [repository.py]
        ├── close_stale_jobs() [repository.py]
        ├── refresh_stale_embeddings() [app/core/llm/embeddings.py]
        ├── populate_for_companies() [company_summary.py] → Tavily API
        └── populate_job_descriptions() [description.py] → Jina AI
```
