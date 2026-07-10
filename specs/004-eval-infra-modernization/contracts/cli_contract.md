# CLI Contract: local_eval.py

The modernized local evaluation script exposes a command-line interface driven by **Typer**.

## Commands

### `evaluate` (Default command)
Run offline evaluation once against a specified search parameter configuration.

```bash
uv run python -m app.evaluation.run_local [OPTIONS]
```

**Parameters & Options**:
- `--bm25` (float): BM25 lexical weight. Range: `[0.0, 1.0]`. Default: `0.1`
- `--vector` (float): Vector semantic weight. Range: `[0.0, 1.0]`. Default: `0.9`
- `--threshold` (float): Cosine distance threshold. Range: `[0.0, 1.0]`. Default: `0.5`
- `--limit` (int): Search result limit. Min: `1`. Default: `20`
- `--per-query` / `--no-per-query`: Flag to print detailed metrics per query. Default: `False`
- `--json` / `--no-json`: Flag to dump final metrics report as a JSON payload. Default: `False`

### `optimize`
Run automated hyperparameter optimization using Optuna.

```bash
uv run python -m app.evaluation.run_local optimize [OPTIONS]
```

**Parameters & Options**:
- `--n-trials` (int): Number of trials to run during hyperparameter search. Min: `1`. Default: `100`
