# Research: Evaluation Infrastructure Modernization

## Decisions & Rationale

### 1. Hyperparameter Optimization (HPO)
* **Decision**: Replace the manual nested-loop grid search in `app/evaluation/run_local.py` with **Optuna**.
* **Rationale**:
  - Optuna is a framework-first, industry-standard HPO library.
  - It replaces 3 levels of nested loops and manual "best score" tracking with a declarative `study.optimize()` execution call.
  - It optimizes the search using algorithms like Tree-structured Parzen Estimator (TPE), finding superior parameters in fewer runs than brute-force grid search.
  - It drastically reduces boilerplate code.
* **Alternatives Considered**:
  - *Keep custom grid-search*: Rejected because it is manual custom infrastructure, violating the Framework-First principle.
  - *LangSmith Experimentation capabilities*: LangSmith can track and record results but does not natively drive parameter suggestion loops for optimization on the client side.

### 2. Regression Detection
* **Decision**: Refactor to a clean, hybrid approach using a thin Python wrapper around the LangSmith Client SDK.
* **Rationale**:
  - LangSmith handles storing results, run metrics, and feed-backs.
  - The custom regression detection logic can be simplified from 50+ lines of custom loop metrics calculations down to a simple API query that compares the current run's average feedback scores against the prior baseline run's average feedback scores.
* **Alternatives Considered**:
  - *Full platform-native*: LangSmith comparison view exists on the web UI, but programmatic pipeline enforcement (CI/CD check exiting with code 1) requires local code execution to query the API.
  - *Alternative evaluation frameworks*: Rejected as it introduces unnecessary abstraction layers.

### 3. CLI Architecture
* **Decision**: Adopt **Typer** to replace `argparse`.
* **Rationale**:
  - Typer is built on Click and uses Python type hints for declarative CLI generation.
  - It provides automatic validation (e.g. ensuring positive integers for limits, floats in ranges) and generates documentation natively.
  - Eliminates over 40 lines of parser setup boilerplate.
* **Alternatives Considered**:
  - *Argparse*: Keep argparse rejected due to high boilerplate overhead and manual type/range checks.
  - *Click*: Click is a solid alternative but requires decorators and lacks Typer's clean type-hint-driven interface.

### 4. Evaluation Orchestration
* **Decision**: Simplify the procedural orchestration structure.
* **Rationale**:
  - Retain SQLAlchemy db queries and the LangSmith `aevaluate` pipeline.
  - Remove manual formatting, printing loops, and custom metrics collection functions.
  - Keep `ir_measures` integration but streamline the output formatting.
* **Alternatives Considered**:
  - *LangChain evaluation wrappers*: Kept minimal, LangSmith-native is simpler and avoids adding unnecessary wrapping classes.

### 5. Configuration Management
* **Decision**: Use the project's existing Pydantic Settings patterns.
* **Rationale**:
  - Ensures settings defaults are loaded cleanly from env files using the existing `Settings` structure.
  - Keeps parameters mapping simple and unified.
