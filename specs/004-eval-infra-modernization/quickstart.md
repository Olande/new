# Quickstart & Validation Guide: Evaluation Infrastructure Modernization

This guide details how to execute and validate the modernized evaluation scripts.

## Prerequisites

Ensure dependencies are installed and the dataset is seeded:
```bash
uv pip install typer optuna
```

## Scenario 1: Execute Single Run Local Evaluation

Evaluate local hybrid search performance with the production settings:
```bash
uv run python -m app.evaluation.run_local --bm25 0.1 --vector 0.9 --threshold 0.5 --per-query
```

**Expected Outcome**:
Prints overall metrics (nDCG@10, nDCG@20, RR, Recall@10, Recall@20) and detailed logs for every benchmark query with its style, matched rank, and computed metric scores.

---

## Scenario 2: Execute Automated Parameter Sweep

Run Optuna optimization to discover optimal retrieval hyperparameters:
```bash
uv run python -m app.evaluation.run_local optimize --n-trials 50
```

**Expected Outcome**:
Optuna trials will execute, logging intermediate trial values. Upon completion, the optimal parameters (BM25 weight, vector weight, similarity threshold) and their corresponding best `nDCG@10` metric score will be printed.

---

## Scenario 3: Platform Regression Detection

Run the remote evaluation and regression check:
```bash
uv run python -m app.evaluation.run_eval
```

**Expected Outcome**:
Runs evaluations on LangSmith, compares average metric results against the prior baseline run, and exits with code `0` if all scores are within acceptable bounds, or exits with code `1` (failing the pipeline) if any metric drops beyond threshold limits.
