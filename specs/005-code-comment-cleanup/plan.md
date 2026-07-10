# Implementation Plan: Code Comment Cleanup

**Branch**: `005-code-comment-cleanup` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-code-comment-cleanup/spec.md`

## Summary

Remove excessive, obvious, and decorative comments from `.py` files outside `app/core/jdl/` to match the clean, minimal-comment style already established in the jdl module. Eight files in `app/evaluation/`, `app/graph/`, `app/mcp/`, and `app/core/llm/` are the primary targets. No functional code changes — only comment deletion and docstring condensation.

## Technical Context

**Language/Version**: Python 3.13+

**Primary Dependencies**: None — no new dependencies required

**Storage**: N/A

**Testing**: `pytest` (existing suite) — all tests must pass with zero changes

**Target Platform**: N/A (code hygiene, no deployment change)

**Project Type**: FastAPI web service (Python)

**Performance Goals**: N/A

**Constraints**:
- FR-008: Zero functional code changes
- FR-005/006: Preserve `Field(description=...)` and tooling pragmas
- All existing tests must pass after cleanup

**Scale/Scope**: ~8 files across 4 packages, ~2,000 lines reviewed, estimated 150-250 comment lines removed

## Constitution Check

*GATE passed — no violations.*

| Principle | Relevance |
|-----------|-----------|
| **III. Rigorous Testing Discipline** | All existing tests must pass after cleanup (SC-004). Review each diff for accidental code changes. |
| **VIII. Simplicity & Minimalist Architecture** | Directly supports this feature. "Code reduction is a valid architectural goal... the solution with fewer lines of code should be preferred." Comment reduction is a form of code reduction that improves readability without changing behavior. |

## Project Structure

### Documentation (this feature)

```text
specs/005-code-comment-cleanup/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions and target list
├── data-model.md        # Phase 1 — N/A (no data model changes)
├── quickstart.md        # Phase 1 — validation guide
├── contracts/           # Phase 1 — N/A (no interface contracts change)
└── checklists/
    └── requirements.md  # Quality checklist
```

### Source Code (repository root)

```text
app/
├── core/
│   └── llm/
│       └── embeddings.py       # Condense verbose docstrings
├── evaluation/
│   ├── metrics.py              # Remove 14 decorative headers + condense docstring
│   ├── run_local.py            # Remove 6 decorative headers + condense docstring
│   ├── run_eval.py             # Remove 4 decorative headers + condense docstring
│   └── search.py               # Remove 4 decorative headers + condense docstring
├── graph/
│   ├── agent.py                # Condense multi-line docstrings, remove obvious inline comments
│   └── nodes.py                # Remove decorative banners + obvious inline comments
└── mcp/
    └── mcp_server.py           # Remove obvious inline restatements

# Excluded (already clean):
#   app/core/jdl/
#   app/core/db/
#   tests/
```

**Structure Decision**: No structural changes — only in-place comment removal/condensation within existing files.

## Implementation Steps

### Step 1 — Remove decorative section headers

Scan each target file for patterns:
- `# ---` (any length)
- `# ===`
- `# ====`
- `# ----------`
- `# Internal ...`
- `# Typer commands`
- `# Main ... flow`

Remove these lines entirely. Do not replace with anything.

**Files**: `metrics.py`, `run_local.py`, `run_eval.py`, `search.py`, `nodes.py`

### Step 2 — Condense module-level docstrings

For each target file with a multi-line module docstring ("""..."""):
- Keep the first sentence describing the module's purpose
- Remove usage examples, CLI syntax, symbol re-export lists, annotated flow diagrams
- Remove any `--help` style documentation that duplicates what the CLI already provides

**Files**: `metrics.py` (15→1 lines), `run_local.py` (17→1 lines), `run_eval.py` (10→1 lines), `search.py` (11→1 lines), `mcp_server.py` (5→1 lines)

### Step 3 — Condense function/class docstrings

For each function docstring longer than 2 lines:
- If the docstring explains internal implementation details, remove it entirely (the code should be self-documenting)
- If the docstring explains the function's contract (what it does, not how), condense to 1-2 lines
- If the function name and signature are self-explanatory, remove the docstring

**Files**: `embeddings.py`, `agent.py`, `nodes.py`

### Step 4 — Remove obvious inline comments

For each inline comment that restates what the code already says:
- `# call the API` above `await call_api()` → remove
- `# create session` above `async_session()` → remove
- `# validate input` above validation code → remove
- `# return result` above `return x` → remove
- Keep comments that explain *why* not *what* (design rationale, business logic, gotchas)

**Files**: `nodes.py` (~50 inline comments), `agent.py`, `mcp_server.py`

### Step 5 — Verify no functional changes

For each modified file:
- Run `git diff` and confirm only comment/docstring lines changed
- Look for any accidental code changes (indentation, line moves, etc.)
- Run full test suite

## Verification

| Check | How | Pass/Fail |
|-------|-----|-----------|
| No decorative headers remain | `rg '# ---|# ===|# ----' app/ --include='*.py'` | Must return 0 hits outside jdl/ |
| Tests pass | `pytest -q` | 34 passed, 0 failed (excluding pre-existing failure) |
| No code changes | `git diff -- app/` | Only comment lines in diff |
| 30% comment reduction | `cloc --by-file diff` or manual line count | Compare before/after |

## Rollback

Each file is a self-contained unit. If a change causes unexpected issues:
- Revert individual files with `git checkout <file>`
- No database migrations or deployment steps involved
