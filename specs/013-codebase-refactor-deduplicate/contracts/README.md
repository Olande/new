# Interface Contracts: Codebase Refactoring

## External Contracts (MCP Tools) — Unchanged

The 6 MCP tool signatures documented in `app/mcp/mcp_server.py` remain identical after refactoring:

| Tool | Input Schema | Output Schema | Status |
|------|-------------|---------------|--------|
| `search_jobs_tool` | `SearchJobsInput` | `SearchJobsOutput` | Unchanged |
| `get_job_tool` | `GetJobInput` | `JobDetailOutput` | Unchanged |
| `get_my_profile_tool` | None | `GetProfileOutput` | Unchanged |
| `create_application_draft_tool` | `CreateApplicationInput` | `CreateApplicationOutput` | Unchanged |
| `submit_application_tool` | `SubmitApplicationInput` | `SubmitApplicationOutput` | Unchanged |
| `confirm_submission_tool` | `ConfirmSubmissionInput` | `ConfirmSubmissionOutput` | Unchanged |

## Internal Contracts — New Shared Utilities

### `app/core/retry_config.py`

```python
# Provided:
DEFAULT_RETRY = RetryConfig(max_attempts=5, ...)

# Usage (decorator factory):
@retry(
    retry=retry_if_exception_type(DEFAULT_RETRY.retryable_exceptions),
    stop=stop_after_attempt(DEFAULT_RETRY.max_attempts),
    wait=wait_exponential_jitter(...),
)
```

### `app/core/batch.py`

```python
async def process_in_batches(
    items: Sequence[T],
    processor: Callable[[T], Awaitable[U]],
    config: BatchProcessorConfig = DEFAULT_BATCH_CONFIG,
) -> list[U | BaseException]:
    """Process items in batches with configurable concurrency and rate limiting."""
```

### `app/core/pagination.py`

```python
async def paginate_api(
    fetch_page: Callable[[int, int], Awaitable[dict]],
    extract_items: Callable[[dict], list[T]],
    config: PaginationParams = DEFAULT_PAGINATION,
) -> AsyncIterator[T]:
    """Generic pagination helper — fetch_page(page, per_page) → extract_items(response) → yield."""
```

### `app/mcp/factory.py`

```python
async def with_service(
    service_factory: Callable[[AsyncSession], T],
    action: Callable[[T], Awaitable[U]],
) -> U:
    """Manage session lifecycle and service instantiation for MCP tools."""
```

See `app/mcp/mcp_server.py` for example MCP tool handler implementations. The factory reduces each tool to:

```python
@mcp.tool(...)
async def some_tool(args...) -> dict:
    inp = SomeInput(...)
    return await with_service(
        lambda s: SomeService(SomeRepo(s)),
        lambda svc: svc.some_method(inp.field),
    )
```
