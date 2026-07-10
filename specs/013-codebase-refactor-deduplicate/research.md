# Research: Codebase Refactoring — Deduplication & Simplification

**Output of Phase 0 — resolves all unknowns from Technical Context.**

## Findings Summary

All design decisions were resolved during the initial analysis and brainstorming session. No NEEDS CLARIFICATION markers remain.

### Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Batch strategy | Two batches (utilities then structural) | Isolates risk — utilities are pure extractions with no behavioral change |
| Retry consolidation | Single shared config in `app/core/retry_config.py` | 4 identical configs with different parameters; central config eliminates drift |
| Batch processor | Shared async utility in `app/core/batch.py` | 3 identical batching patterns; parameterizes batch size, concurrency, error handling |
| Pagination utility | Extracted to `app/core/pagination.py` | Inline cursor logic hard to test in isolation |
| Field mapping | Centralize via Pydantic model method or `model_dump()` | Pydantic already provides serialization; eliminate manual dict builders |
| MCP boilerplate | Factory/helper in `app/mcp/factory.py` | All 6 tools share identical session→repo→service→call→return pattern |
| Skill normalization | Replace with `dict.fromkeys()` / `itertools.unique_everseen` | Stdlib equivalents already available |
| In-flight dedup | Replace Event+lock with shared `asyncio.Future` | Simpler, fewer lines, same behavior |
| `nodes.py` split | Split by concern: query, scoring, submission | Aligns with existing function groupings and LangGraph phases |
| Test file split | `conftest.py` + per-module test files | Standard pytest convention; shared fixtures extracted once |

### Dependencies Check

| Dependency | Usage | Alternative |
|------------|-------|-------------|
| tenacity | Retry library — keep; consolidate config | No alternative needed |
| aiolimiter | Rate limiting — keep | Already used, no duplication |
| asyncio | In-flight dedup — keep; simplify pattern | stdlib, no alternative |
| itertools | `unique_everseen` for skill dedup | stdlib |
| Pydantic | `model_dump()` for central field mapping | Already project dependency |

### Integration Patterns

- **Shared utilities** follow the existing `app.core` pattern — new helpers in `app/core/batch.py`, `app/core/retry_config.py`, `app/core/pagination.py`
- **Test fixtures** follow `conftest.py` convention already used in other test files
- **Module splitting** preserves `__init__.py` re-exports for backward compatibility where needed
