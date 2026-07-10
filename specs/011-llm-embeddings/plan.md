# Implementation Plan: LLM Embeddings

**Branch**: Multiple (iterative) | **Status**: Migrated | **Spec**: `specs/011-llm-embeddings/spec.md`

## Summary

Generate, store, and refresh vector embeddings for jobs using Google's Gemini Embedding API. The pipeline is deterministic — each embedding stores a hash of its input text so unchanged jobs skip re-embedding. Batched with concurrency control and retry for resilience.

## Technical Context

**Language/Version**: Python 3.13+, LangChain `GoogleGenerativeAIEmbeddings`
**Primary Dependencies**: `langchain-google-genai` (embedding client), `google-api-core` (error types), `tenacity` (retry), `pgvector` (storage)
**Storage**: PostgreSQL — `embeddings` table with `vector(1024)` column
**Testing**: ❌ No dedicated test file

## Data Flow

```
Discovery Cycle
    │
    └─→ refresh_stale_embeddings(session)
            │
            ├─ fetch_active_jobs() → all active jobs
            ├─ fetch_existing_embeddings() → existing embeddings by job_id
            │
            └─ collect_stale_jobs()
                    │
                    ├─ compute_job_embedding_hash(job)  ← SHA-256 of versioned text
                    ├─ needs_embedding_update()          ← hash mismatch OR expired
                    │
                    └─ [stale jobs] → embed_texts_in_batches()
                            │
                            ├─ split into batches of 10
                            ├─ semaphore: max 3 concurrent
                            ├─ retry: 5 attempts, exponential jitter
                            └─ Google Gemini Embedding API
                                    │
                                    └─ apply_embedding_update() → INSERT/UPDATE Embedding
```

## Embedding Text Construction

```python
JobEmbeddingDocument(
    title=job.title,
    company=job.company_name,
    role=job.role,
    function=job.job_function,
    seniority=job.seniority,
    employment=job.employment_type,
    remote=job.remote_type,
    locations=job.locations,
    skills=job.required_skills,
    description=job.description.cleaned_text,    # from JobDescription
    company_summary=job.company_summary,
)
# Serialized as: "title:Senior ML Engineer\ncompany:Acme\nskills:Python..."
```

## Key Design Decisions

1. **Hash-based skip**: SHA-256 of `v{version}:{text}` avoids redundant API calls — if the job metadata hasn't changed, the hash matches and no API call is made
2. **Validity window**: 7-day `valid_until` ensures embeddings are periodically refreshed even if content hasn't changed (catches model updates)
3. **Versioned text format**: `EMBEDDING_TEXT_VERSION` constant — bumping it invalidates all existing hashes, forcing a full re-embed
4. **Gemini-specific**: Uses `GoogleGenerativeAIEmbeddings` directly (not a generic interface) — model name and dimensions are explicit
