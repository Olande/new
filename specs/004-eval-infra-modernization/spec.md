# Feature Specification: Evaluation Infrastructure Modernization

**Feature Branch**: `004-eval-infra-modernization`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "Review the evaluation and retrieval benchmarking modules. Goals: Eliminate manual orchestration where supported libraries already exist. Prefer framework-native solutions over custom implementations. Reduce total lines of code. Preserve evaluation behavior and metrics. Evaluate replacing or simplifying: Manual grid-search loops, Manual regression detection, Manual experiment comparison, Manual metric aggregation, Manual ranking collection orchestration, Manual CLI argument parsing. Investigate capabilities in: LangSmith, LangChain evaluation tooling, Optuna, Pydantic Settings / CLI integrations, Typer, Existing retrieval evaluation libraries. Requirements: Maintain SQLAlchemy. Maintain LangSmith as the experiment platform. Preserve current metrics. Preserve current dataset format. Reduce custom infrastructure code wherever possible. Deliver: 1. Current-state architecture review. 2. Libraries capable of replacing custom implementations. 3. Estimated LOC reduction. 4. Recommended target architecture. 5. Migration plan."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Regression Detection (Priority: P1)

Developers must be able to run benchmarking/evaluation experiments on a retrieval dataset and automatically detect if the candidate search algorithm version degrades retrieval quality compared to a prior baseline.

**Why this priority**: Preventing regression in retrieval quality is the most critical requirement for system reliability. If a regression occurs, the development pipeline must immediately notify the team.

**Independent Test**: Can be tested by running the evaluation command on a set of retrieval candidate changes with known degraded performance. The command must exit with a non-zero code and log regression warnings.

**Acceptance Scenarios**:

1. **Given** a configured evaluation dataset in the experiment platform, and a prior baseline run, **When** the developer executes the evaluation suite, **Then** the system computes metrics, compares them against the baseline, and fails if the drop exceeds defined thresholds.
2. **Given** a new candidate run that does not degrade retrieval performance, **When** the evaluation is executed, **Then** the system completes successfully with no warnings.

---

### User Story 2 - Automated Hyperparameter Optimization (Priority: P2)

Developers need to run parameter sweep and optimization tasks to discover optimal combinations of retrieval parameters (e.g. search weights and distance thresholds) without manual grid loops.

**Why this priority**: Optimizing retrieval performance requires sweeping parameters. Manual nested loops are inefficient and hard to scale when new parameters are added.

**Independent Test**: Can be tested by running the parameter search command locally. It should output the best parameter combination discovered along with its performance metrics.

**Acceptance Scenarios**:

1. **Given** search ranges for retrieval weights and distance thresholds, **When** the search command is executed, **Then** the system automatically finds the parameter set that maximizes target retrieval metrics.

---

### User Story 3 - Local Benchmarking CLI with Input Validation (Priority: P3)

Developers need a simple, self-documenting Command Line Interface (CLI) to run single-run evaluations and sweeps locally with validation of inputs.

**Why this priority**: CLI usage is the primary interaction point for offline tuning and validation. Invalid parameter inputs must be caught immediately before triggering heavy DB search queries.

**Independent Test**: Can be tested by executing the local benchmarking CLI with invalid parameters (e.g. weights out of range or negative limit). The CLI should print validation errors and exit gracefully without hitting the database.

**Acceptance Scenarios**:

1. **Given** the benchmarking CLI tool, **When** a user provides valid parameters, **Then** it executes the benchmark and prints the metrics formatted clearly.
2. **Given** the benchmarking CLI tool, **When** a user inputs invalid parameters, **Then** the CLI raises immediate input validation errors and stops execution.

---

### Edge Cases

- **Empty Database/Index**: If the local database is not populated or index is empty, the system must handle the absence of search results gracefully (metrics should be computed as zero or indicated appropriately) rather than crashing with division-by-zero or database connection exceptions.
- **Missing Dataset or Prior Run**: If the benchmark dataset or baseline experiment is missing on the remote platform, regression detection must fall back to a warning/log notification rather than crashing, letting the current candidate run proceed and be saved.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support executing retrieval evaluations against a remote experiment tracking platform dataset.
- **FR-002**: The system MUST automatically compare candidate run metrics (specifically nDCG@10 and MRR) against a baseline/prior run and signal a regression if the relative drop exceeds configured thresholds.
- **FR-003**: The system MUST support parameter sweeps (optimization) for retrieval parameters including BM25 weight, vector weight, and distance threshold to find optimal values.
- **FR-004**: The system MUST aggregate retrieval metrics (nDCG@10, nDCG@20, RR, Recall@10, Recall@20) overall and group them by query style metadata.
- **FR-005**: The benchmarking CLI MUST validate that user-provided search parameters fall within acceptable physical bounds (e.g. weights sum to 1.0, distance threshold is between 0.0 and 1.0, result limit is positive).
- **FR-006**: The system MUST preserve compatibility with the current database mapping (SQLAlchemy) and the current dataset format.

### Key Entities

- **Evaluation Dataset**: Represents the collection of benchmark queries, query styles, and expected golden job outputs.
- **Search Parameter Configuration**: The set of retrieval parameters (weights, thresholds, and limits) that control the candidate hybrid search algorithm.
- **Evaluation Report**: The aggregated metrics (nDCG, Recall, Reciprocal Rank) overall and partitioned by query styles.
- **Regression Threshold**: The configuration that defines acceptable drop margins for each retrieval metric before signaling a pipeline failure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the current evaluation metrics (overall and per query style) are preserved and produce mathematically equivalent results under the modernized system.
- **SC-002**: Evaluation run script setup boilerplates and CLI configuration code are reduced by at least 40% in lines of code compared to the current implementation.
- **SC-003**: The system successfully tracks and records experiments on the designated tracking platform (LangSmith) without altering the dataset schema.
- **SC-004**: Parameter optimization runs complete without manual grid nesting loops in the user-written application codebase.

## Assumptions

- **A-001**: The database (PostgreSQL with pgvector) is already set up and schema migrations are handled by SQLAlchemy.
- **A-002**: LangSmith will continue to be used as the remote experiment tracking platform.
- **A-003**: No new search metrics are required beyond the existing set of nDCG, Reciprocal Rank, and Recall.
