# LOC Reduction & Library Adoption Audit Report

This report outlines opportunities to reduce maintenance burden and replace custom logic with established Python libraries or framework capabilities, preserving functionality while minimizing Lines of Code (LOC).

## Quick Wins

### 1. HTTP Client Retry Configuration
*   **File(s) affected:** `app/core/retry_config.py`, `app/core/jdl/client.py`
*   **Current implementation:** The project implements a custom `RetryConfig` class wrapping `tenacity` along with `httpx_retries.RetryTransport`.
*   **Replacement approach:** Tenacity is already installed. The custom configuration abstraction `RetryConfig` in `app/core/retry_config.py` can be replaced with direct `tenacity` decorators (`@retry(wait=wait_exponential_jitter(...), stop=stop_after_attempt(...))`). Since HTTPX 0.28+ provides some built-in retry functionality (or the existing `httpx_retries` can be used uniformly without the parallel tenacity wrapper).
*   **Estimated LOC reduction:** ~30 LOC
*   **Risk level:** Low

### 2. Tenant Context Middleware & Thread Locals
*   **File(s) affected:** `app/mcp/mcp_context.py`, `app/mcp/mcp_server.py`
*   **Current implementation:** `mcp_context.py` implements custom `ContextVar` management for tenant ID and user ID. `mcp_server.py` implements a custom ASGI middleware `TenantMiddleware`.
*   **Replacement approach:** Use FastAPI's or Starlette's `Request.state` object for request-scoped context, combined with standard dependency injection (`Depends`), instead of custom `ContextVar` plumbing. If FastMCP requires middleware, this can still leverage standard Starlette capabilities rather than manual thread locals where possible.
*   **Estimated LOC reduction:** ~50 LOC
*   **Risk level:** Low

## Medium Impact Refactors

### 1. Custom Pagination & Batch Processing
*   **File(s) affected:** `app/core/pagination.py`, `app/core/batch.py`, `app/core/jdl/client.py`
*   **Current implementation:** `app/core/pagination.py` provides custom `PaginationParams` and an async generator `paginate_api`. `app/core/batch.py` implements a custom semaphore-based `process_in_batches` with `aiolimiter`.
*   **Replacement approach:** For batch processing with semaphores and rate limiting, the `aiolimiter` library is good, but `asyncio.TaskGroup` (Python 3.11+) combined with simple `itertools.batched` removes the need for custom batching logic wrapping `asyncio.gather`. For pagination, standard async generators without the bespoke `PaginationParams` class abstraction would be cleaner.
*   **Estimated LOC reduction:** ~100 LOC
*   **Risk level:** Medium

### 2. Custom Exception Translation
*   **File(s) affected:** `app/mcp/exceptions.py`, `app/mcp/mcp_server.py`
*   **Current implementation:** `app/mcp/exceptions.py` defines a custom exception hierarchy (`DomainException`, `NotFoundError`, etc.) and a custom decorator `@translate_mcp_exceptions`.
*   **Replacement approach:** FastMCP and FastAPI both natively support global exception handlers. Instead of decorating every tool in `mcp_server.py` with `@translate_mcp_exceptions`, register a global exception handler in the server/app initialization.
*   **Estimated LOC reduction:** ~40 LOC
*   **Risk level:** Medium

### 3. Service Layer Thin Wrappers
*   **File(s) affected:** `app/mcp/services/app_service.py`, `app/mcp/services/job_service.py`, `app/mcp/factory.py`, `app/mcp/mcp_server.py`
*   **Current implementation:** `app/mcp/factory.py` implements a custom `with_service` dependency injection wrapper. `mcp_server.py` manually instantiates repositories and services using this wrapper for every tool call (e.g., `lambda s: JobService(JobRepository(s)...)`).
*   **Replacement approach:** FastMCP is a wrapper around FastAPI/Starlette concepts. Use standard dependency injection (e.g., FastDepends, which FastMCP can integrate with, or standard contextual injection) instead of the manual `with_service` higher-order function and manual constructor chains.
*   **Estimated LOC reduction:** ~80 LOC
*   **Risk level:** Medium

## High Impact Opportunities

### 1. Optuna Hyperparameter Optimization Scripts
*   **File(s) affected:** `app/evaluation/run_local.py`, `app/evaluation/run_eval.py`
*   **Current implementation:** `run_local.py` has a full custom async wrapper for Optuna `optimize` and custom evaluation metric computation. `run_eval.py` implements custom regression thresholds and checks pulling from LangSmith feedback.
*   **Replacement approach:** LangSmith has native evaluation and dataset testing capabilities. The custom Optuna search and the custom threshold checking logic can be largely replaced by using LangSmith's built-in evaluation capabilities (e.g., `aevaluate` which is already partially used). By standardizing fully on LangSmith, the custom regression logic (`check_retrieval_regression`, relative drop calculations) can be replaced by LangSmith CI/CD assertions.
*   **Estimated LOC reduction:** ~150-200 LOC
*   **Risk level:** Medium

### 2. Job Validation and Normalization
*   **File(s) affected:** `app/core/jdl/normalization.py`
*   **Current implementation:** Manually implemented data cleaning, date parsing with explicit `isoparse` try/catch, and explicit custom Pydantic validators in `RawJobInput`.
*   **Replacement approach:** Pydantic v2 has incredibly robust native type coercion for datetimes (handling ints, floats, strings natively). The `parse_date_field` and custom location extractors can be simplified by relying on native Pydantic aliases (`AliasPath` or `AliasChoices`, which are already partially used) and native datatime parsing, removing the need for manual `fromtimestamp` and exception handling logic.
*   **Estimated LOC reduction:** ~50 LOC
*   **Risk level:** Low

## Estimated LOC Reduction

Implementing all the recommendations above would result in removing approximately **500 - 550 Lines of Code (LOC)** across the codebase, simplifying maintenance, reducing potential surface area for bugs, and delegating work to more robust standard libraries and framework-native features.

## Final Recommendation (Ranked)

1. **Job Validation and Normalization:** (Low Risk, ~50 LOC, Low Effort). Remove custom date parsing and trust Pydantic v2 coercion.
2. **Custom Exception Translation:** (Medium Risk, ~40 LOC, Low Effort). Use standard exception handlers instead of the custom decorator.
3. **HTTP Client Retry Configuration:** (Low Risk, ~30 LOC, Low Effort). Delete custom config wrapper; use tenacity directly.
4. **Service Layer Thin Wrappers:** (Medium Risk, ~80 LOC, Medium Effort). Remove `with_service` and use standard DI.
5. **Custom Pagination & Batch Processing:** (Medium Risk, ~100 LOC, Medium Effort). Simplify batch processing with standard `asyncio`.
6. **Optuna Hyperparameter Optimization:** (Medium Risk, ~200 LOC, High Effort). Migrate custom tuning and regression checks fully to LangSmith's native feature set.
