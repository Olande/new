# Implementation Plan: Codebase Refactoring — Deduplication & Simplification

**Branch**: `013-codebase-refactor-deduplicate` | **Date**: 2026-07-11 | **Spec**: spec.md

**Input**: Feature specification from `specs/013-codebase-refactor-deduplicate/spec.md`

## Summary

Eliminate code duplication, reduce file sizes, and replace custom implementations with standard library equivalents across the CareerPilot codebase. Delivered in two batches: utility-focused extractions (retry config, batch processor, field mapper, pagination helper, MCP boilerplate) followed by structural changes (split god files, extract data from logic, simplify patterns, split test files).

## Technical Context

**Language/Version**: Python 3.13+

**Primary Dependencies**: FastAPI, LangGraph, LangChain, SQLAlchemy 2.0, pgvector, tenacity, httpx, aiolimiter, asyncio

**Storage**: PostgreSQL 16 with pgvector extension (via SQLAlchemy async + Alembic migrations)

**Testing**: `pytest` with `pytest-asyncio` — `uv run pytest tests/`

**Linting**: `uv run ruff check app/ tests/` — zero warnings required

**Project Type**: Backend API service + MCP server + background daemon

**Constraints**: Zero behavior change — refactoring must preserve all existing outputs, schemas, and contracts.

**Scope**: 6 production files + 2 test files, ~2,000 lines affected across batches.

## Constitution Check

*GATE: Passes — this refactoring directly implements Constitution Principles VI (Framework-First) and VIII (Simplicity & Minimalist Architecture).*

- ✅ **Language**: Python 3.13+ — unchanged
- ✅ **Framework**: FastAPI / LangGraph — unchanged
- ✅ **Storage**: PostgreSQL + pgvector — unchanged
- ✅ **Modules**: Changes scoped to `app/core/`, `app/graph/`, `app/mcp/`, `tests/`
- ✅ **Dependencies**: No new dependencies — all improvements use existing libraries or stdlib
- ✅ **Principle VI (Framework-First)**: Every replacement uses existing library capabilities (tenacity, stdlib, existing patterns)
- ✅ **Principle VIII (Simplicity)**: Directly reduces LOC, abstractions, duplication, and maintenance points
- ✅ **Principle III (Testing)**: All existing tests must pass; no behavior changes allowed
- ✅ **Principle I (Decoupled Architecture)**: Shared utilities belong in `app/core/`; extraction improves module isolation
- ⚠️ **No violations** — no complexity tracking needed

## Project Structure

```
specs/013-codebase-refactor-deduplicate/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 — unresolved decisions
├── data-model.md        # Phase 1 — entity definitions
├── quickstart.md        # Phase 1 — validation guide
├── contracts/           # Phase 1 — interface contracts
└── tasks.md             # Created by /speckit-tasks
```

## Complexity Tracking

None required — no constitution violations.

## Execution Plan

### Batch 1 — Utilities (P1)

| Step | Module | Target File(s) | New File |
|------|--------|----------------|----------|
| 1.1 | Shared retry config | `description.py`, `company_summary.py`, `embeddings.py`, `search.py` | `app/core/retry_config.py` |
| 1.2 | Shared batch processor | `company_summary.py`, `description.py` | `app/core/batch.py` |
| 1.3 | Shared pagination utility | `client.py:search_all_results()` | `app/core/pagination.py` |
| 1.4 | Central field mapping | `job_fallback_service.py`, `search.py`, `repository.py`, `job_repo.py` | `app/core/mapping.py` or extend existing schema |
| 1.5 | MCP boilerplate factory | `mcp_server.py` (6 tools) | `app/mcp/factory.py` |
| 1.6 | Simplify skill normalization & dedup | `normalization.py` | Inline refactor |
| 1.7 | Simplify in-flight dedup | `job_fallback_service.py` | Inline refactor |

### Batch 2 — Structural (P2→P3)

| Step | Module | Target File(s) | New File(s) |
|------|--------|----------------|-------------|
| 2.1 | Split `nodes.py` | `app/graph/nodes.py` (454 lines) | `app/graph/query_nodes.py`, `app/graph/scoring_nodes.py`, `app/graph/submission_nodes.py` |
| 2.2 | Extract eval data | `scripts/seed_eval_datasets.py` | `scripts/eval_data.py` (or `app/evaluation/eval_data.py`) |
| 2.3 | Split test files | `tests/test_fallback.py` (812 lines) | `tests/conftest.py`, `tests/test_jdl_client.py`, `tests/test_job_repo.py`, `tests/test_fallback_service.py` |
