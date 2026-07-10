# Quickstart: Codebase Refactoring — Deduplication & Simplification

**Validation scenarios** to verify refactoring correctness.

## Prerequisites

- Python 3.13+ with `uv` installed
- Running PostgreSQL 16 with pgvector (or mock — tests use mocking)

## Setup

```bash
uv sync
```

## Validation Scenarios

### Scenario 1: All existing tests pass (SC-007)

Run after **each** refactoring step:

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

**Expected**: All tests pass. Zero failures. Same test count as before the step.

### Scenario 2: Ruff lint passes (SC-008)

```bash
uv run ruff check app/ tests/
```

**Expected**: Zero warnings. Exit code 0.

### Scenario 3: Field mapping equivalence (SC-004)

After centralizing field mappings, run the specific schema/output tests:

```bash
uv run pytest tests/test_fallback.py -v -k "job_hit or search_jobs_output or job_detail" --tb=short
```

**Expected**: All schema tests pass with identical output structure.

### Scenario 4: Retry config consolidation (SC-005)

No automated test — manual code review to verify all 4 callers use the shared config:

```bash
grep -rn "@retry" app/ | grep -v __pycache__
```

**Expected**: Only one `@retry` decorator definition in `app/core/retry_config.py`; all others import from it.

### Scenario 5: Batch pattern consolidation (SC-006)

After extraction, verify the old patterns are gone:

```bash
grep -rn "batched.*gather\|asyncio\.gather.*return_exceptions" app/ --include="*.py"
```

**Expected**: No output (all gather calls route through `process_in_batches()`).

### Scenario 6: Batch 2 structural — graph tests pass

After splitting `nodes.py`:

```bash
uv run pytest tests/test_graph.py -v --tb=short
```

**Expected**: All graph tests pass.

### Scenario 7: File size limits (SC-002, SC-003)

```bash
# Check no app file exceeds 250 lines
find app -name "*.py" -exec wc -l {} + | awk '$1 > 250' | sort -rn

# Check no test file exceeds 400 lines
find tests -name "*.py" -exec wc -l {} + | awk '$1 > 400' | sort -rn
```

**Expected**: No output (or only files you intentionally left unchanged).

### Scenario 8: LOC reduction (SC-001)

```bash
# Before any changes — take baseline
find app -name "*.py" ! -path "*/migrations/*" -exec wc -l {} + | tail -1
# After refactoring — should be >=15% lower
```

**Expected**: Production code (excluding `alembic/`) reduced by at least 15%.

## Per-Step Checklist

| Step | Verification Command(s) | Key Risk |
|------|------------------------|----------|
| 1.1 Retry config | SC-004 manual review | Different backoff params per module |
| 1.2 Batch processor | SC-005 grep, S1 test suite | Exception handling behavior |
| 1.3 Pagination | S1 test suite | Edge case: single page vs multi-page |
| 1.4 Field mapping | S3 schema tests | Missing field in output |
| 1.5 MCP factory | S1 test suite | Tool request/response mismatch |
| 1.6 Normalization | S1 test suite | Different hash output for same input |
| 1.7 In-flight dedup | S1 test suite | Race condition in concurrent tests |
| 2.1 Split nodes | S6 graph tests | Wrong import path in agent.py |
| 2.2 Extract eval data | Manual seed run | Dataset differs after extraction |
| 2.3 Split test files | S1 full test suite | Missing fixture import |
