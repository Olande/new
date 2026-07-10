# MCP Tool Contracts: API Job Fallback

**Feature**: `012-api-job-fallback` | **Date**: 2026-07-10

This document defines the **modified MCP tool interface contracts** for
`search_jobs_tool` and `get_job_tool` after the fallback feature is implemented.

---

## Tool: `search_jobs_tool`

**Location**: `app/mcp/mcp_server.py` → delegates to `JobService.search_jobs()`

### Input Schema (unchanged)

```python
class SearchJobsInput(BaseModel):
    query: str = Field(..., min_length=2, max_length=500,
                       description="Natural language job search query")
    limit: int = Field(default=10, ge=1, le=20, description="Max results")
    cosine_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
```

No input changes — the caller interface is identical to the pre-fallback version.

### Output Schema (extended)

```python
class SearchJobsOutput(BaseModel):
    hits: list[JobHit]
    total: int
    fallback_used: bool = False   # NEW: True when JDL API was called
    dropped_count: int = 0        # NEW: jobs dropped due to normalization failures
```

```python
class JobHit(BaseModel):
    id: str
    title: str
    company_name: str
    required_skills: list[str] = []
    remote_type: str | None = None
    locations: list[str] = []
    score: float
    fallback_source: str | None = None  # NEW: "jdl_api" or None
```

### Behavior Contract

| Condition | `fallback_used` | `hits` source | `dropped_count` |
|-----------|----------------|----------------|----------------|
| DB hits ≥ threshold | `False` | DB only | `0` |
| DB hits < threshold, API succeeds | `True` | DB (after upsert + re-query) | ≥ 0 |
| DB hits < threshold, API fails | `False` | DB only (may be empty) | `0` |
| `fallback_enabled=False` | `False` | DB only | `0` |

### Error Handling

- JDL API unavailable → returns `SearchJobsOutput(hits=[], total=0, fallback_used=False)`
  (no exception raised to the MCP caller)
- Rate limit exhausted → same as API unavailable
- JDL API key missing → same; logged as WARNING at startup

---

## Tool: `get_job_tool`

**Location**: `app/mcp/mcp_server.py` → delegates to `JobService.get_job()`

### Input Schema (unchanged)

```python
class GetJobInput(BaseModel):
    job_id: UUID = Field(..., description="Job UUID from search results")
```

### Output Schema (extended)

```python
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
    fallback_source: str | None = None  # NEW: "jdl_api" or None
```

### Behavior Contract

| Condition | Result |
|-----------|--------|
| Job found in local DB | Returns full `JobDetailOutput`, `fallback_source=None` |
| Job absent from DB, found in JDL API | Upserts job, returns `JobDetailOutput` with `fallback_source="jdl_api"` |
| Job absent from DB and JDL API | Raises `NotFoundError` → MCP returns error response |
| JDL API unreachable | Raises `NotFoundError` (same as not found) |
| `fallback_enabled=False` | Raises `NotFoundError` immediately if not in DB |

### Error Response (via existing `NotFoundError`)

```json
{
  "error": true,
  "message": "Job {job_id} not found or inactive",
  "code": "tool_error"
}
```

---

## Backward Compatibility

All changes are **additive**:
- New output fields have safe defaults (`None`, `False`, `0`)
- Existing callers receive the same data they always did; new fields are extras
- No input schema changes — no caller migration required
- MCP protocol version unchanged

---

## Source Attribution Values

| `fallback_source` value | Meaning |
|-------------------------|---------|
| `null` / `None` | Job discovered via batch JDL discovery pipeline |
| `"jdl_api"` | Job fetched on-demand via API fallback |

Future sources (e.g., `"manual_entry"`, `"partner_feed"`) reserved for later.
