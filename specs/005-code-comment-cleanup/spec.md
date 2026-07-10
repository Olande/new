# Feature Specification: Code Comment Cleanup

**Feature Branch**: `005-code-comment-cleanup`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "make the other code be clean like the jdl folder, no excessive comments, just clean code"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Read clean code without visual noise (Priority: P1)

As a developer reading the codebase, I want files outside `app/core/jdl/` to have the same minimal commenting style as the jdl module, so I can focus on what the code does without filtering out decorative headers and obvious inline notes.

**Why this priority**: This is the entire value of the feature — code is read far more often than it is written, and excessive comments reduce signal-to-noise ratio.

**Independent Test**: A reviewer can open any modified file and verify it has no decorative `# ---` section headers, no inline comments that restate the obvious, and only concise 1-line docstrings where needed.

**Acceptance Scenarios**:

1. **Given** a file that previously had `# ----` section dividers, **When** the file is opened, **Then** no decorative section headers remain.
2. **Given** a function with a multi-paragraph docstring explaining obvious internals, **When** the file is opened, **Then** that docstring is either removed or condensed to a single line describing the function's contract.
3. **Given** an inline comment like `# call the API` above `await call_api()`, **When** the file is opened, **Then** that comment is removed.

---

### User Story 2 — Consistent commenting style across the codebase (Priority: P2)

As a maintainer onboarding to a new module, I want the commenting style to be uniform regardless of which module I'm reading, so I don't have to mentally switch between verbose and terse conventions.

**Why this priority**: Consistency reduces cognitive overhead and establishes a clear convention for new code.

**Independent Test**: A style lint rule or manual spot-check across any 5 randomly chosen app modules shows no decorative headers or obvious inline comments.

**Acceptance Scenarios**:

1. **Given** any file in `app/evaluation/`, `app/graph/`, `app/mcp/`, or `app/core/llm/`, **When** scanned for `# ---`, `# ===`, or `# ----` patterns, **Then** none are found.
2. **Given** a developer reviewing a PR, **When** they see a comment, **Then** it conveys non-obvious information (design rationale, business rule, gotcha) rather than restating the code.

---

### Edge Cases

- What happens when a docstring contains a meaningful API contract or type explanation that isn't obvious from the signature? → Keep it, but shorten to 1-2 lines.
- What about Pydantic `Field(description=...)` values? → Keep them — those serve as OpenAPI schema descriptions and are part of the API contract, not code comments.
- What about `# noqa` or `# type: ignore` pragmas? → Keep them — they affect tooling behavior, not human readability.
- What about module-level docstrings that explain module purpose? → Keep a single concise line, remove usage examples that duplicate what the CLI `--help` already shows.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All decorative section headers (`# ---`, `# ===`, `# ----`, `# ----------`) MUST be removed from every file outside `app/core/jdl/`.
- **FR-002**: Inline comments that restate the obvious (e.g., `# create session` above `async_session()`) MUST be removed.
- **FR-003**: Multi-paragraph docstrings on simple functions MUST be condensed to at most 2 lines or removed entirely when the function name and signature are self-explanatory.
- **FR-004**: Module-level docstrings MUST be limited to one line describing the module's purpose. Usage examples and symbol indexes MUST be removed.
- **FR-005**: `Field(description=...)` values MUST be preserved — they are OpenAPI schema metadata, not code comments.
- **FR-006**: Tooling pragmas (`# noqa`, `# type: ignore`) MUST be preserved.
- **FR-007**: Comments that document non-obvious design rationale, business rules, or known gotchas MUST be preserved and optionally shortened.
- **FR-008**: No functional code changes MAY be introduced — only comment removal/condensation is permitted.

### Key Entities

- **Comment types**: Decorative headers (`# ---`), verbose docstrings, inline obvious-restating comments, module-level usage docs, API-metadata descriptions.
- **Target files**: Any `.py` file in `app/` outside `app/core/jdl/` that exhibits the decorative/verbose patterns listed above.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All `# ---`, `# ===`, `# ----` decorative header patterns are eliminated from every file outside `app/core/jdl/`.
- **SC-002**: No function docstring exceeds 2 lines unless it documents a non-obvious design rationale or business rule.
- **SC-003**: Comment-to-code ratio in modified files drops measurably (at least 30% reduction in comment lines).
- **SC-004**: All existing tests pass with zero changes to test expectations — proving no functional code was altered.
- **SC-005**: A developer unfamiliar with the codebase can open any 3 modified files and identify zero instances of obvious inline restatements.

## Assumptions

- **Scope boundary**: `app/core/db/` (models, migrations) and `app/core/jdl/` are already clean and out of scope.
- **Test stability**: No test files need modification since only comments are removed.
- **Preserved descriptions**: Pydantic `Field(description=...)` values stay — they serve a different purpose than code comments.
- **Tooling pragmas**: `# noqa`, `# type: ignore`, and similar directives are preserved since they affect tool behavior.
- **No re-review needed**: The cleanup should not require re-approval of business logic since no code changes.
