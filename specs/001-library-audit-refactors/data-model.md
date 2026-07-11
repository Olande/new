# Data Model Reference: Library Audit & Refactoring

**Purpose**: Field-name parity reference for Step 4 (`model_dump()` refactor). The data model itself does not change — this document confirms that `JobCreate.model_dump(exclude={"source"})` produces the exact field set needed for both upsert paths.

## JobCreate (source for model_dump)

```python
class JobCreate(JobBase):
    dedup_hash: str
    status: str = "active"
    source: JobSourceCreate        # ← excluded from model_dump for upserts
```

Fields inherited from `JobBase`:

| Field | Type | Nullable |
|-------|------|----------|
| title | str | No |
| company_name | str | No |
| domain_name | str \| None | Yes |
| role | str \| None | Yes |
| job_function | str \| None | Yes |
| seniority | list[str] | No (default []) |
| employment_type | str \| None | Yes |
| remote_type | str \| None | Yes |
| locations | list[str] | No (default []) |
| countries | list[str] | No (default []) |
| required_skills | list[str] | No (default []) |
| employee_count | str \| None | Yes |
| funding | str \| None | Yes |
| posted_at | datetime \| None | Yes |

## Job ORM (upsert target — SQLAlchemy, `jobs` table)

| Column | Type | Source |
|--------|------|--------|
| id | UUID | auto-generated |
| dedup_hash | str | JobCreate |
| title | str | JobCreate |
| company_name | str | JobCreate |
| domain_name | str \| None | JobCreate |
| role | str \| None | JobCreate |
| job_function | str \| None | JobCreate |
| seniority | list[str] | JobCreate |
| employment_type | str \| None | JobCreate |
| remote_type | str \| None | JobCreate |
| locations | list[str] | JobCreate |
| countries | list[str] | JobCreate |
| required_skills | list[str] | JobCreate |
| employee_count | str \| None | JobCreate |
| funding | str \| None | JobCreate |
| company_summary | str \| None | Tavily fetch (not in JobCreate) |
| status | str | JobCreate ("active") |
| posted_at | datetime \| None | JobCreate |
| last_seen_at | datetime | runtime-generated |
| created_at | datetime | server default (never upserted) |
| fallback_source | str \| None | runtime-set (job_repo.py only) |

## Upsert Dict Construction — Before vs After

### `upsert_job` (repository.py)

**Current** (manual dict):
```python
values = {
    "dedup_hash": normalized.dedup_hash,
    "title": normalized.title,
    ...
    "status": "active",
    "posted_at": normalized.posted_at,
    "last_seen_at": now_utc,
}
```

**After** (model_dump):
```python
values = normalized.model_dump(exclude={"source"}) | {"last_seen_at": now_utc}
```

`model_dump()` already includes `status` (default "active") and `posted_at`. The only addition is `last_seen_at`.

### `upsert_from_fallback` (job_repo.py)

**Current** (manual dict per job):
```python
job_rows.append({
    "id": job_id,                    # auto-generated UUID
    "dedup_hash": j.dedup_hash,
    ...
    "status": "active",
    "posted_at": j.posted_at,
    "fallback_source": "jdl_api",    # runtime-set
    "last_seen_at": now,
})
```

**After** (model_dump):
```python
vals = j.model_dump(exclude={"source"})
vals.update({"id": job_id, "fallback_source": "jdl_api", "last_seen_at": now})
job_rows.append(vals)
```

## Verification

Before deploying Step 4, generate the dict key-sets from both old and new code paths and diff them:

```python
# Run this in a Python shell or test:
from app.core.jdl.schemas import JobCreate

old_keys = {
    "dedup_hash", "title", "company_name", "domain_name", "role",
    "job_function", "seniority", "employment_type", "remote_type",
    "locations", "countries", "required_skills", "employee_count",
    "funding", "status", "posted_at", "last_seen_at",
}

sample = JobCreate(
    title="x", company_name="x", dedup_hash="x",
    source__source_name="x", source__source_job_id="x",
    source__source_url="x", source__first_seen_at="2024-01-01",
)
new_keys = set(sample.model_dump(exclude={"source"}).keys()) | {"last_seen_at"}

assert old_keys == new_keys, f"Key mismatch: {old_keys ^ new_keys}"
```
