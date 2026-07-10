# Research: Code Comment Cleanup

No external research was needed — this feature is purely a code hygiene exercise with no new technologies, dependencies, or integrations.

## Decision

**Approach**: Manual review of target files with automated pattern checks for verification.

**Rationale**: Comment cleanup requires human judgment to distinguish between:
- Obvious inline restatements (remove)
- Decorative section headers (remove)
- Verbose docstrings that explain internals (condense)
- Semantically meaningful comments about design rationale or business rules (preserve)
- Pydantic `Field(description=...)` values (preserve — they're OpenAPI schema metadata)
- Tooling pragmas (`# noqa`, `# type: ignore`) (preserve)

A pure regex/automated approach cannot make this distinction reliably.

## Target Files

From the initial audit (`/speckit.specify` scanning), the files with the most excessive comments are:

| File | Issue |
|------|-------|
| `app/evaluation/metrics.py` | 14 `# ---` section headers, 15-line module docstring |
| `app/graph/nodes.py` | 3 `# ---` banners, 50+ inline obvious comments |
| `app/evaluation/run_local.py` | 6 `# ---` headers, 17-line module docstring |
| `app/evaluation/search.py` | 4 `# ---` headers, 11-line module docstring |
| `app/evaluation/run_eval.py` | 4 `# ---` headers, 10-line module docstring |
| `app/core/llm/embeddings.py` | Verbose docstrings on trivial functions |
| `app/graph/agent.py` | Multi-line docstrings on every function, obvious inline checks |
| `app/mcp/mcp_server.py` | Inline comments restating obvious tool-route setup |

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Automated regex strip-all-comments | Would destroy semantically meaningful comments, Field descriptions, and tooling pragmas |
| Ruff `flake8-comments` lint rule | No existing rule captures the "obvious restatement" distinction; would require custom plugin |
| AI bulk rewrite | Risk of introducing subtle functional changes (FR-008); wasteful for a purely mechanical task |
