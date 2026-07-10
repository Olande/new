"""Backward-compatible CLI wrapper around ``app.evaluation.run_local``.

Prefer:
  uv run python -m app.evaluation.run_local
  uv run python -m app.evaluation.run_local --grid
  uv run python -m app.evaluation.run_local --bm25 0.1 --vector 0.9 --threshold 0.5
"""

from app.evaluation.run_local import main

if __name__ == "__main__":
    main()
