# Data Model: Codebase Refactoring — Deduplication & Simplification

**Phase 1 artifact** — defines the entity contracts for shared utilities.

## Shared Utilities

### BatchProcessorConfig

Represents the configuration for the shared async batch-processing utility.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `batch_size` | int | 10 | Number of items to process per batch |
| `max_concurrency` | int | 3 | Maximum concurrent in-flight tasks |
| `return_exceptions` | bool | True | Whether to return exceptions per-item instead of failing the batch |
| `rate_per_second` | float | None | Optional rate limit (requests per second) |

**States**: N/A — stateless configuration object.

### RetryConfig

Centralized retry configuration used by all external API callers.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_attempts` | int | 5 | Maximum retry attempts |
| `initial_wait` | float | 1.0 | Initial backoff in seconds |
| `max_wait` | float | 60.0 | Maximum backoff in seconds |
| `retryable_exceptions` | tuple[Exception] | `(httpx.HTTPStatusError, httpx.ReadTimeout, httpx.ConnectTimeout, ResourceExhausted, ServiceUnavailable)` | Exception types that trigger retry |

**States**: N/A — stateless configuration.

### PaginationParams

Parameters for the shared pagination helper (replaces inline cursor in `client.py`).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `per_page` | int | 50 | Items per API page |
| `max_results` | int | None | Maximum total items to yield |
| `page_cap` | int | 50 | Maximum pages to fetch |

**States**: N/A — config object consumed by pagination iterator.

### JobFieldMapper

Contract for mapping ORM `Job` objects to output DTOs. Implemented via Pydantic `model_dump()` with optional field overrides.

**Fields** (shared across `JobHit`, `JobDetailOutput`, `JobSearchResult`):

| Field | Source | Target(s) | Transformation |
|-------|--------|-----------|----------------|
| `id` | `job.id` | string | `str(job.id)` |
| `title` | `job.title` | string | direct |
| `company_name` | `job.company_name` | string | direct |
| `required_skills` | `job.required_skills` | list[str] | `list(job.required_skills or [])` |
| `remote_type` | `job.remote_type` | string or None | direct |
| `locations` | `job.locations` | list[str] | `list(job.locations or [])` |
| `score` / `rrf_score` | `job.rrf_score` | float | `getattr(job, 'rrf_score', 0.0)` |
| `fallback_source` | `job.fallback_source` | string or None | direct |
| `seniority` | `job.seniority` | list[str] | `list(job.seniority or [])` |
| `employment_type` | `job.employment_type` | string or None | direct |
| `description` | `job.description.cleaned_text` | string | eagerly loaded; `""` if not loaded |

**Validation rules**: No DTO field should require a manual converter — mapping must be derivable from the source model definition.

## Relationships

```
Job (ORM model)
  ├── JobHit (search result, 9 fields)
  ├── JobDetailOutput (detail view, 10 fields)
  ├── JobSearchResult (internal, 8 fields)
  └── JobCreate (input schema, 15 fields)
        └── JobSourceCreate (embedded)

Shared utilities (no DB entities):
  ├── BatchProcessorConfig → consumed by process_in_batches()
  ├── RetryConfig → consumed by all tenacity-decorated functions
  └── PaginationParams → consumed by paginate_api()
```

## State Transitions

None — this is a pure refactoring spec. All data flows remain identical.
