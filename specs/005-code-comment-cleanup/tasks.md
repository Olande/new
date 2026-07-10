# Tasks: Code Comment Cleanup

**Input**: Design documents from `/specs/005-code-comment-cleanup/`

**Prerequisites**: plan.md, spec.md, research.md

**Tests**: Not requested — cleanup is comment-only; existing test suite validates correctness.

**Organization**: Tasks are grouped by user story (package-aligned) so each increment is independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Establish baseline state and confirm starting conditions.

- [x] T001 Run full test suite and record baseline: `uv run pytest -q`
- [x] T002 [P] Scan for existing decorative headers across target files: `rg '# ---|# ===|# ----' app/evaluation/ app/graph/ app/mcp/ app/core/llm/ --include='*.py' -n`
- [x] T003 [P] Review each target file's comment style and note which patterns to keep (Field descriptions, noqa, design rationale comments per FR-005/006/007)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Read each file identified in the plan and confirm understanding of what constitutes:
  - Decorative header (`# ---`, `# ===`, `# ----`, `# ----------`)
  - Verbose module docstring (multi-line with usage examples)
  - Verbose function docstring (implementation details, >2 lines)
  - Obvious inline comment (restates what the code does)
  - Keep-worthy comment (design rationale, business rule, gotcha)

**Checkpoint**: Foundation ready — cleanup can begin on any file independently.

---

## Phase 3: User Story 1 — Read clean code without visual noise (Priority: P1) 🎯 MVP

**Goal**: Remove decorative headers and condense module/function docstrings in the `evaluation/` package — the most comment-heavy part of the codebase.

**Independent Test**: Open any file in `app/evaluation/` — confirm no `# ---` headers remain and module docstrings are ≤1 line describing purpose only.

### Implementation for User Story 1

- [x] T005 [P] [US1] Remove decorative `# ---` section headers from `app/evaluation/metrics.py` (14 headers) per plan Step 1
- [x] T006 [P] [US1] Remove decorative `# ---` section headers from `app/evaluation/run_local.py` (6 headers) per plan Step 1
- [x] T007 [P] [US1] Remove decorative `# ---` section headers from `app/evaluation/run_eval.py` (4 headers) per plan Step 1
- [x] T008 [P] [US1] Remove decorative `# ---` section headers from `app/evaluation/search.py` (4 headers) per plan Step 1
- [x] T009 [US1] Condense module docstring in `app/evaluation/metrics.py` to 1 line (currently 15 lines with public-symbol bullet list) per plan Step 2
- [x] T010 [US1] Condense module docstring in `app/evaluation/run_local.py` to 1 line (currently 17 lines with CLI usage examples) per plan Step 2
- [x] T011 [US1] Condense module docstring in `app/evaluation/run_eval.py` to 1 line (currently 10 lines with annotated flow diagram) per plan Step 2
- [x] T012 [US1] Condense module docstring in `app/evaluation/search.py` to 1 line (currently 11 lines with re-export list) per plan Step 2
- [x] T013 [P] [US1] Condense verbose function docstrings in `app/core/llm/embeddings.py` — replace multi-line docstrings with at most 1 line describing function contract per plan Step 3

**Checkpoint**: All `evaluation/` package files are clean — module docstrings are 1 line, no decorative headers, function docstrings are concise.

---

## Phase 4: User Story 2 — Consistent commenting style across the codebase (Priority: P2)

**Goal**: Extend the same treatment to `graph/`, `mcp/`, and `core/llm/` — remove decorative banners, condense function docstrings, and strip obvious inline comments.

**Independent Test**: Spot-check `app/graph/nodes.py` and `app/graph/agent.py` — confirm no inline comments restate the obvious, and function docstrings are ≤2 lines unless documenting non-obvious rationale.

### Implementation for User Story 2

- [x] T014 [P] [US2] Remove decorative `# ---` banners from `app/graph/nodes.py` (3 banners) per plan Step 1
- [x] T015 [P] [US2] Condense verbose multi-line docstrings in `app/graph/nodes.py` — shorten to ≤2 lines per function, remove implementation-detail explanations per plan Step 3
- [x] T016 [US2] Remove obvious inline comments from `app/graph/nodes.py` (~50 inline restatements like `# r.value is dict like...` and play-by-play comments) per plan Step 4
- [x] T017 [P] [US2] Condense verbose multi-line docstrings in `app/graph/agent.py` — replace implementation-detail docstrings (5-12 lines) with 1-2 line function contract per plan Step 3
- [x] T018 [US2] Remove obvious inline comments from `app/graph/agent.py` (inline sanity-check comments that restate obvious checks) per plan Step 4
- [x] T019 [P] [US2] Condense module docstring in `app/mcp/mcp_server.py` to 1 line (currently 5 lines describing architecture) per plan Step 2
- [x] T020 [US2] Remove obvious inline restatement comments from `app/mcp/mcp_server.py` (comments like `# Primary FastMCP instance`, `# Input validation via Pydantic DTO` that restate what code shows) per plan Step 4

**Checkpoint**: All 8 target files cleaned — consistent minimal-comment style across all touched modules.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Verify correctness, format, and full test pass.

- [x] T021 Run `ruff check app/ --fix` and `ruff format app/` to ensure consistent formatting after edits
- [x] T022 Run `git diff -- app/` and verify only comment/docstring lines changed — zero functional code changes (SC-004)
- [x] T023 Run `rg '# ---|# ===|# ----|# ====' app/ --include='*.py'` and confirm zero hits (SC-001)
- [x] T024 Run full test suite: `uv run pytest -q` and confirm same baseline (34 passed, 1 pre-existing failure)
- [x] T025 Final manual spot-check of 3 randomly chosen modified files to confirm no obvious inline restatements remain (SC-005)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (must know what to keep vs remove)
- **US1 (Phase 3)**: Depends on Phase 2 completion
- **US2 (Phase 4)**: Depends on Phase 2 completion — can run after or alongside US1 (different file sets)
- **Polish (Phase 5)**: Depends on both US1 and US2 being complete

### User Story Dependencies

- **US1 (P1) — `evaluation/` package**: Self-contained — touches zero files that US2 touches
- **US2 (P2) — `graph/`, `mcp/`, `llm/` packages**: Self-contained — touches zero files that US1 touches

The two user stories operate on disjoint file sets:
| User Story | Files | Packages |
|------------|-------|----------|
| US1 | `metrics.py`, `run_local.py`, `run_eval.py`, `search.py`, `embeddings.py` | `evaluation/`, `core/llm/` |
| US2 | `nodes.py`, `agent.py`, `mcp_server.py` | `graph/`, `mcp/` |

### Within Each User Story

- Docstring condensation before inline comment removal (avoid double-editing same functions)
- Core (logic-heavy) files before leaf files
- Verify with `git diff` after each file

### Parallel Opportunities

- All Phase 1 tasks marked [P] can run in parallel
- All tasks within US1 marked [P] can run in parallel (different `app/evaluation/` files)
- All tasks within US2 marked [P] can run in parallel (different `app/graph/` files)
- US1 and US2 can run in parallel (disjoint file sets) — recommended

---

## Parallel Example: User Story 1

```bash
# Launch all evaluation/ file cleanup in parallel:
Task: "Remove decorative headers from metrics.py"
Task: "Remove decorative headers from run_local.py"
Task: "Remove decorative headers from run_eval.py"
Task: "Remove decorative headers from search.py"
Task: "Condense function docstrings in embeddings.py"

# Then condense module docstrings (can also be parallel):
Task: "Condense module docstring in metrics.py"
Task: "Condense module docstring in run_local.py"
Task: "Condense module docstring in run_eval.py"
Task: "Condense module docstring in search.py"
```

## Parallel Example: User Story 2

```bash
# Launch all graph/ + mcp/ cleanup in parallel:
Task: "Remove banners + condense docstrings in nodes.py"
Task: "Condense docstrings + strip inline comments in agent.py"
Task: "Condense module docstring + strip inline comments in mcp_server.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup — run baseline tests, scan headers
2. Complete Phase 2: Foundational — understand keep vs. remove criteria
3. Complete Phase 3: User Story 1 — clean all `evaluation/` + `embeddings.py`
4. **STOP and VALIDATE**: Run Phase 5 verification (ruff format, git diff check, rg scan, pytest)
5. The `evaluation/` package is the most comment-heavy — cleaning it delivers the most visible improvement

### Incremental Delivery

1. US1 complete → `evaluation/` package clean and testable
2. US2 complete → `graph/`, `mcp/`, `llm/` packages also clean
3. Polish complete → Full verification suite passed

### Parallel Team Strategy

With two developers:
1. Developer A: Phase 3 (US1) — `evaluation/` package + `embeddings.py`
2. Developer B: Phase 4 (US2) — `graph/` + `mcp/` files
3. Both run parallel, then together verify in Phase 5

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story operates on disjoint file sets — no merge conflicts
- Preserve `Field(description=...)`, `# noqa`, `# type: ignore`, and non-obvious design rationale comments
- Zero functional code changes permitted
- Verify with `git diff` after each file — only comment lines should appear
