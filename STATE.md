# Loop State — fun-project (careerpilot)

Last run: 2026-07-10T18:30:00+03:00 (L1 report-only triage)

---

## High Priority (loop is acting on or waiting on human)

1. **Worktree `fun_project_eval_modernization` (branch `004-eval-infra-modernization`) has significant uncommitted changes** — The evaluation consolidation commit (`477e8ad`) landed on `phase4-infra-decoupling`. The remaining loop infrastructure and code changes were moved to a dedicated worktree:
   - **What's staged in worktree**: Loop infra files (LOOP.md, STATE.md, opencode.json, skills/, loop-budget.md, loop-constraints.md, loop-run-log.md) + spec 001
   - **What's unstaged in worktree**: Substantial graph agent refactoring — `agent.py` (+98 lines: new Postgres persistence factory, submission nodes, llm_critic), `nodes.py` (+233 lines: intent router, prepare_submission, request_human_approval, execute_submission, llm_critic, store migration), `graph_state.py` (+32 lines: CritiqueResult, submission HIL fields, user_id, verification_attempts)
   - **New untracked dirs**: `specs/002-phases-3-4-lean/`, `specs/003-refactor-mcp-tools/`, `specs/004-eval-infra-modernization/` — all with full spec+plan+tasks
   - **New untracked code**: `app/mcp/` (full MCP server with repositories/services/schemas), `tests/test_mcp.py`, `tests/test_graph.py`
   - **Dependencies added**: `optuna`, `typer`, `colorlog`
   - **Action**: Review the scope of changes in the worktree. This mixes loop infra, graph agent refactoring, MCP server, and 3 new specs — consider splitting into smaller, focused PRs.
   - Effort: medium

2. **Tests broken in worktree — all 3 test files fail during collection** — `test_evaluation.py`, `test_graph.py`, `test_mcp.py` all error with `sqlalchemy.exc.ArgumentError: Expected string or URL object, got None`:
   - Root cause: Tests need a database URL (DATABASE_URL env var) to import `app.core.db.base` and `app.core.config.settings`
   - This is a pre-existing issue (tests need DB env), not caused by recent changes
   - Main repo tests at `477e8ad` pass (17/17) because they run a different subset
   - **Action**: Either document the required env setup for tests, or add `.env.example` and a pytest fixture that skips DB-dependent tests when no DB is configured.
   - Effort: low

3. **Stash `stash@{0}` on `phase4-infra-decoupling` contains duplicate of worktree changes** — The loop infrastructure files and code changes were stashed before creating the worktree. The stash is now a stale duplicate. **Action**: Drop the stash to avoid confusion (`git stash drop stash@{0}`).
   - Effort: trivial

## Watch Items

- **Model configuration in `nodes.py`**: `get_frontier_model` uses `gemini-3.1-flash-lite` (was `deepseek-v4-pro`). `get_fast_model` uses `gemini-2.5-flash` (was `deepseek-v4-flash`). This model switch was flagged in previous triage and is still unconfirmed as intentional.
- **`test.ipynb` has massive modifications** (384 insertions, 104 deletions) — includes significant code restructuring and notebook execution metadata. Should be cleaned before commit. The diff shows new cells with graph state definitions and model initializations that mirror production code.
- **`Dockerfile.db` and `move_docker.sh` remain untracked** — present in both main repo and worktree. Either commit or gitignore.
- **No open GitHub issues** — still zero across all branches.
- **Graphify graph is at commit `477e8ad`**, current with main branch. Stale relative to worktree changes.

## Noise / Ignored

- Dual `GOOGLE_API_KEY` / `GEMINI_API_KEY` warning from google-genai — cosmetic, same as before.
- `__pycache__` directories — properly ignored.
- `uv.lock` changes are dependency additions (optuna, typer, colorlog) — part of the worktree's feature work.
- `pyproject.toml` changes in worktree add optuna and typer dependencies — intentional for eval infra modernization.

## State Updates

- **Main branch**: `phase4-infra-decoupling` at `477e8ad` (clean). Tests: 17/17 pass.
- **Worktree branch**: `004-eval-infra-modernization` at `477e8ad` (diverged). Staged: loop infra files + spec 001. Unstaged: graph agent refactoring (agent.py, nodes.py, graph_state.py). Untracked: app/mcp/, specs/002/003/004, tests/test_graph.py, tests/test_mcp.py.
- **Stash `stash@{0}`**: Contains all files now in worktree. Candidate for deletion.
- **Tests (worktree)**: 0/3 pass — all fail at collection due to missing DATABASE_URL.
- **Tests (main)**: 17/17 pass.
- **No CI failures observed** (last push was commit `477e8ad`).
- **No open GitHub issues.**

## Run Log Entry

```json
[
  {
    "run_id": "2026-07-10T18:30:00+03:00",
    "pattern": "l1-report-only-triage",
    "duration_s": 75,
    "items_found": 5,
    "actions_taken": 1,
    "escalations": 0,
    "outcome": "Report-only triage. Large commit 477e8ad landed on phase4-infra-decoupling (eval consolidation + AGENTS.md). Loop infra and code changes moved to worktree 004-eval-infra-modernization with substantial graph agent refactoring (agent.py +98, nodes.py +233), new MCP server, and 3 new specs. Tests broken in worktree (missing DATABASE_URL). Stash@{0} is stale duplicate of worktree."
  },
  {
    "run_id": "2026-07-10T14:10:00+03:00",
    "pattern": "l1-report-only-triage",
    "duration_s": 90,
    "items_found": 6,
    "actions_taken": 0,
    "escalations": 0,
    "outcome": "Report-only triage. Large staged commit (28 files, 911 insertions, 266 deletions) consolidates evaluation framework, adds real tests, fixes CI/gitignore. Unstaged further refactoring (tenacity, lru_cache, partials, cleanup). All 14 tests pass. Model switch to gemini needs review. test.ipynb has execution noise."
  },
  {
    "run_id": "2026-07-10T14:00:00+03:00",
    "pattern": "l1-report-only-triage",
    "duration_s": 60,
    "items_found": 5,
    "actions_taken": 0,
    "escalations": 0,
    "outcome": "Report-only triage. 9/9 graph tests pass; no CI failures; no open issues. Flagged missing tests/ dir, stale CI path filters, untracked tool dirs (.grok, .agents, .specify). All evaluations and scoring graphs stable."
  },
  {
    "run_id": "2026-07-10T13:25:00+03:00",
    "pattern": "fix-score-candidate-attribute-error",
    "duration_s": 240,
    "items_found": 1,
    "actions_taken": 3,
    "escalations": 0,
    "outcome": "Updated score_candidate to accept dict input; added test_score_candidate_success unit test; verified all 9 tests pass; updated graphify knowledge graph."
  },
  {
    "run_id": "2026-07-10T01:40:00+03:00",
    "pattern": "eval-framework-rebuild",
    "duration_s": 600,
    "items_found": 2,
    "actions_taken": 8,
    "escalations": 0,
    "outcome": "Rebuilt retrieval evaluation under app/evaluation; fixed no_match poisoning; production params score nDCG@10=0.7367 RR=0.7059"
  }
]
```
