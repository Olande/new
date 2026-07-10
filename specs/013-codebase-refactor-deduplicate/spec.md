# Feature Specification: Codebase Refactoring — Deduplication & Simplification

**Feature Branch**: `013-codebase-refactor-deduplicate`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "The project is almost done but the problem is that it has God files, large files > 250 lines, numerous duplications in which most of the work could be joined or deduplicated, your goal is to find them and generate a spec to handle the deduplication of the logic, reduce the loc significantly, remove the reinvented wheels, use python libraries instead of reinventing logic"

## Project Context

This feature targets **CareerPilot AI** — a FastAPI + LangGraph + PostgreSQL (pgvector) backend.

## Code Quality Analysis Summary

### Large Files (>250 lines)

| File | Lines | Issues |
|------|-------|--------|
| `tests/test_fallback.py` | 812 | Massive test file with repetitive mock/fixture setup |
| `app/graph/nodes.py` | 454 | God node file — mixing memory migration, submissions, search, critiquing |
| `tests/test_evaluation.py` | 295 | Repetitive mock helper patterns |
| `scripts/seed_eval_datasets.py` | 288 | Data mixed with logic — golden jobs and examples embedded as literals |
| `app/evaluation/metrics.py` | 276 | Well-structured but includes presentation logic (formatting) |
| `app/mcp/services/job_fallback_service.py` | 272 | Converter methods duplicate field mapping from schemas |

### Duplication Hotspots

1. **Field mapping duplication**: `JobHit` / `JobDetailOutput` / `JobSearchResult` share ~80% field overlap; `_job_to_detail_output()` / `_hits_from_raw()` / `run_search()` all manually map identical fields.

2. **Batch processing pattern** repeated identically in 3 files:
   - `company_summary.py:populate_company_summaries()` + `populate_for_companies()` — same batching → gather → error handling
   - `description.py:populate_job_descriptions()` — same batched + gather + response processing

3. **DB upsert field mapping** duplicated between `repository.py:upsert_job()` and `job_repo.py:upsert_from_fallback()` — both build identical dicts of job fields.

4. **MCP tool handler boilerplate** — all 6 tools in `mcp_server.py` follow identical session → repo → service → call → return pattern.

5. **Tenacity retry config duplication** — each of `description.py`, `company_summary.py`, `embeddings.py`, `search.py` defines its own retry config.

### Reinvented Wheels

1. Custom whitespace normalization & dedup hash (`normalization.py`) — `re` + `hashlib` reimplemented when `unicodedata` + standard hashing suffice.
2. In-flight dedup with `asyncio.Event` + lock (`job_fallback_service.py`) — over-engineered; shared `asyncio.Future` with single waiter is simpler.
3. Page-pagination loop (`client.py:search_all_results`) — no existing pagination utility used.
4. Skill normalization via manual `seen` dict — `dict.fromkeys()` or `itertools.unique_everseen` exists in stdlib.

1. Custom whitespace normalization & dedup hash (`normalization.py`) — `re` + `hashlib` reimplemented when `unicodedata` + standard hashing suffice.
2. In-flight dedup with `asyncio.Event` + lock (`job_fallback_service.py`) — over-engineered; shared `asyncio.Future` with single waiter is simpler.
3. Page-pagination loop (`client.py:search_all_results`) — no existing pagination utility used.
4. Skill normalization via manual `seen` dict — `dict.fromkeys()` or `itertools.unique_everseen` exists in stdlib.

## User Scenarios & Testing

### User Story 1 — Extract reusable batch-processing utility (Priority: P1)

As a developer maintaining CareerPilot, I want a single shared `async_batch_processor` utility so that the three identical batched-gather patterns in the codebase are replaced with one function call.

**Why this priority**: Highest ROI — 3 locations collapse to 1 utility, reducing ~120 lines of near-identical code.

**Independent Test**: Can be verified by running the existing tests for company_summary, description, and embeddings pipelines after migrating each to the shared utility.

**Acceptance Scenarios**:

1. **Given** the shared batch processor exists, **When** `company_summary.py` and `description.py` both use it, **Then** the batch/gather/error-handle pattern appears in exactly one place.
2. **Given** any batch processor call, **When** one item fails with an exception, **Then** the remaining items in the batch still complete and the error is logged.
3. **Given** a batch processor call with `return_exceptions=True`, **When** all items fail, **Then** the function returns empty results without raising.

---

### User Story 2 — Centralize field mapping schemas (Priority: P1)

As a developer adding a new field to job search results, I want to change it in one place rather than updating 4+ converter functions across the codebase.

**Why this priority**: Reduces maintenance surface — 6 mapping locations collapse to 2 (source schema + auto-generated converters).

**Independent Test**: All search/detail output tests pass after migration, with identical output structure.

**Acceptance Scenarios**:

1. **Given** the centralized field mapping, **When** a new field is added to `JobHit`, **Then** no converter function needs manual updates.
2. **Given** the current output, **When** migrated, **Then** every output field produces the same value as before migration.

---

### User Story 3 — Split God files into focused modules (Priority: P2)

As a developer onboarding to the project, I want `app/graph/nodes.py` split into focused modules (search, scoring, submission, memory) so that each file has a single responsibility and is under 200 lines.

**Why this priority**: Reduces cognitive load — 454-line god file obscures boundaries between unrelated concerns.

**Independent Test**: All graph-related tests pass after migration without changes to the graph wiring.

**Acceptance Scenarios**:

1. **Given** the current `nodes.py`, **When** split by concern, **Then** the original file is removed and each new file is under 200 lines.
2. **Given** the split modules, **When** the LangGraph agent is instantiated, **Then** all nodes are importable and function identically.

---

### User Story 4 — Consolidate retry configurations (Priority: P2)

As a developer debugging an API timeout, I want a single shared retry configuration in `app/core` so that all modules use the same backoff strategy and I can tune it centrally.

**Why this priority**: Reduces config drift — 4 different retry configs exist, each with different attempt counts and backoff parameters.

**Independent Test**: Existing tests pass after retry refactor with same timeouts/attempts.

**Acceptance Scenarios**:

1. **Given** the shared retry config exists, **When** all 4 modules use it, **Then** retry config is defined in exactly one location.
2. **Given** the shared config, **When** parameters are changed, **Then** all consumers pick up the change.

---

### User Story 5 — Eliminate reinvented wheel patterns (Priority: P3)

As a reviewer, I want to see standard Python idioms replace custom dedup hashing, skill normalization, and in-flight dedup implementations so the codebase is easier to understand and maintain.

**Why this priority**: Lower urgency but improves code clarity and reduces ~80 lines of custom logic.

**Independent Test**: All existing normalization and dedup tests pass after replacement.

**Acceptance Scenarios**:

1. **Given** the skill normalization function, **When** refactored to use `dict.fromkeys()`, **Then** behavior is identical for all input cases.
2. **Given** the in-flight dedup, **When** refactored to use shared `asyncio.Future`, **Then** concurrent duplicate queries are still deduplicated.

---

### User Story 6 — Move test data out of logic (Priority: P3)

As a developer, I want the golden job definitions and eval example data in `seed_eval_datasets.py` moved to a separate config/data file so I can edit test fixtures without touching execution code.

**Why this priority**: Separation of concerns — data and logic are currently interleaved in a 288-line script.

**Independent Test**: Seeding produces identical LangSmith datasets before and after migration.

**Acceptance Scenarios**:

1. **Given** the current `seed_eval_datasets.py`, **When** data is extracted to a data module, **Then** the script file shrinks by at least 60%.
2. **Given** the extracted data, **When** imported by the seed script, **Then** the same examples and golden jobs are produced.

---

### User Story 7 — Split large test files (Priority: P2)

As a developer debugging a test failure, I want `tests/test_fallback.py` split into focused test modules matching the production module layout, so I can find relevant tests by filename rather than scrolling through 800+ lines.

**Why this priority**: 812-line test file makes it hard to locate tests for specific modules and encourages copy-paste test patterns.

**Independent Test**: All tests pass after split with same test count and coverage.

**Acceptance Scenarios**:

1. **Given** the current `test_fallback.py` (812 lines), **When** split by tested module (e.g., client tests, repository tests, service tests), **Then** each new file is under 400 lines.
2. **Given** the split test files, **When** `uv run pytest tests/` is executed, **Then** all original tests pass with identical test IDs.
3. **Given** shared fixtures in current `test_fallback.py`, **When** extracted to a `tests/conftest.py`, **Then** they are reusable across the split test modules.

As a developer, I want the golden job definitions and eval example data in `seed_eval_datasets.py` moved to a separate config/data file so I can edit test fixtures without touching execution code.

**Why this priority**: Separation of concerns — data and logic are currently interleaved in a 288-line script.

**Independent Test**: Seeding produces identical LangSmith datasets before and after migration.

**Acceptance Scenarios**:

1. **Given** the current `seed_eval_datasets.py`, **When** data is extracted to a data module, **Then** the script file shrinks by at least 60%.
2. **Given** the extracted data, **When** imported by the seed script, **Then** the same examples and golden jobs are produced.

---

### Edge Cases

- Refactoring must not change output format of any MCP tool or API endpoint — existing consumers depend on exact field names.
- Splitting `nodes.py` must preserve LangGraph node function signatures — the graph wiring in `agent.py` references them by name.
- Synchronous batch processor must not introduce deadlocks with existing async patterns.

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide a shared async batch-processing utility that accepts items, an async processing function, batch size, and optional concurrency limit.
- **FR-002**: The batch utility MUST handle exceptions per-item without aborting the entire batch.
- **FR-003**: System MUST centralize Job → DTO field mappings so that no more than 2 locations define the same field transformation.
- **FR-004**: `app/graph/nodes.py` MUST be split into at least 3 modules: memory/search (node functions related to query analysis and retrieval), scoring (ranking/critique), and submission (application submission flow).
- **FR-005**: System MUST provide a shared retry configuration at a central location with configurable attempt count and backoff.
- **FR-006**: All existing retry definitions MUST be replaced by the shared retry config from FR-005.
- **FR-007**: Custom skill normalization MUST be replaced with standard library equivalents to achieve the same behavior with fewer lines of custom code.
- **FR-008**: In-flight dedup in `job_fallback_service.py` MUST be simplified by replacing the Event+lock pattern with a simpler concurrency primitive that achieves the same deduplication behavior.
- **FR-009**: Golden job data and eval examples from `seed_eval_datasets.py` MUST be extracted into a separate data module.
- **FR-010**: MCP tool boilerplate in `mcp_server.py` MUST be reduced so that the session → repo → service → call → return pipeline is defined once and reused across all tools.
- **FR-011**: All refactored code MUST pass existing tests (zero regressions).
- **FR-012**: All refactored code MUST pass `ruff check` with zero new warnings.
- **FR-013**: `tests/test_fallback.py` MUST be split into multiple files by tested module (client, repository, service), each under 400 lines.
- **FR-014**: Shared test fixtures currently in `test_fallback.py` MUST be extracted to `tests/conftest.py` for reuse across split modules.
- **FR-015**: The manual pagination loop in `client.py:search_all_results()` MUST be extracted into a shared pagination utility to eliminate the inline page-cursor logic.

### Key Entities

- **BatchProcessorConfig**: Batch size, concurrency limit, error handling strategy
- **RetryConfig**: Attempt count, backoff parameters, retryable exception types
- **JobFieldMapper**: Single mapping definition from ORM model to output schema fields

### Database Migrations

None required — this is a pure refactoring spec. No schema changes.

### API Contract

**No changes to MCP tool signatures or output shapes** — this is backward-compatible refactoring.

### Graph Agent Changes

- `app/graph/nodes.py` — will be split, not removed. Node function signatures stay the same so edges/routing in `agent.py` are unaffected.
- No changes to `graph_state.py` or `agent.py`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Total lines of production code (excluding tests) reduced by at least 15%.
- **SC-002**: No file in `app/` exceeds 250 lines (current max: 454).
- **SC-003**: No test file in `tests/` exceeds 400 lines (current max: 812).
- **SC-004**: Number of locations defining job field → DTO mappings reduced from 6 to at most 2.
- **SC-005**: Number of tenacity retry config definitions reduced from 4 to 1.
- **SC-006**: Number of batch/gather/error-handle pattern occurrences reduced from 3 to 1.
- **SC-007**: All existing tests pass with zero changes to test assertions.
- **SC-008**: All refactored modules pass `ruff check app/ tests/` with zero warnings.

## Assumptions

- Existing tests provide sufficient coverage to catch regressions introduced by refactoring.
- The LangGraph agent's node wiring (`agent.py`) references node functions by module path — splitting `nodes.py` will require updating imports in `agent.py`.
- MCP tool consumers (the human user prompting the MCP server) do not depend on internal file structure, only on tool names and output shapes.
- `ruff` format will be run on all modified files to maintain consistent style.
- The refactoring will be done incrementally, one module at a time, with tests passing at each step.
- Implementation will proceed in **two batches**: batch 1 (utilities) then batch 2 (structural).
- **Batch 1 order**: retry config → batch processor → field mapper → MCP boilerplate.
- **Batch 2 order**: split `nodes.py` → extract eval data → simplify patterns → split test files.

## Dependencies

- Requires existing test suite to be comprehensive enough to catch regressions.
- No external library additions needed — all improvements use existing dependencies or stdlib.

## Brainstorm Log

### 2026-07-11 — Initial brainstorm session

- **Q1 (Scope granularity)**: Chose **Option C — two batches**: utilities first, structural changes second.
- **Q2 (Test files)**: Chose **Option A — in-scope**: `test_fallback.py` (812 lines) will be split and fixtures extracted to `conftest.py`. Added as User Story 7 (FR-013, FR-014).
- **Q3 (Batch 2 order)**: Chose **Option A**: split `nodes.py` → extract eval data → simplify patterns → split test files.
- **Q4 (Pagination loop)**: Chose **Option A — refactor**: extract pagination loop into shared utility (FR-015).
- **Key insight**: The 9 original user stories collapsed to 7 after merging related items. 15 functional requirements cover all identified hotspots.
- **Design approved**: Two-batch plan with clear ordering accepted.
