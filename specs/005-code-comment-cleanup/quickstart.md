# Quickstart: Code Comment Cleanup Validation

## Prerequisites

- Python 3.13+
- `uv` package manager
- `.venv/` with all dependencies installed (`uv sync`)
- Git repository on `phase4-infra-decoupling` branch

## Validate Before Cleanup

Run the test suite to establish baseline:

```bash
uv run pytest -q
```

Note the count: expected **34 passed, 1 failed** (`test_grounded_claims_pass_through` — pre-existing, unrelated).

## Run Cleanup

Follow the steps in [plan.md](./plan.md) Implementation Steps 1–5. Each file is edited manually with human judgment:

1. Remove decorative `# ---` headers
2. Condense module docstrings
3. Condense function docstrings
4. Remove obvious inline comments
5. Verify no functional code changes

## Validate After Cleanup

### Check 1 — No decorative headers remain

```bash
rg '# ---|# ===|# ----|''# ----------' app/ --include='*.py' -n 2>/dev/null || echo "None found"
```

Expected: no matches outside `app/core/jdl/`.

### Check 2 — All tests pass

```bash
uv run pytest -q
```

Expected: same result as baseline — **34 passed, 1 failed** (same pre-existing failure).

### Check 3 — No functional code changes

```bash
git diff -- app/ | grep '^[+-]' | grep -v '^[+-]#' | grep -v '^[+-][[:space:]]*#' | grep -v '^[+-][[:space:]]*$' | grep -v '^[+-]{3}' || echo "No code changes detected"
```

Expected: only comment lines (`+#` or `-#`) in diff. No `+` or `-` lines that start with actual code.

### Check 4 — Comment reduction

```bash
# Before (if not yet committed)
git stash && cloc app/evaluation/ app/graph/ app/mcp/ app/core/llm/ --by-file 2>/dev/null | rg '\.py' | awk '{s+=$4} END{print s " comment lines"}'
git stash pop
```

Or simpler — review `git diff --stat` to see lines removed.
