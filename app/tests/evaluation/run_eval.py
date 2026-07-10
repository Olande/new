"""Shim — LangSmith CI entrypoint lives in ``app.evaluation.run_eval``."""

from app.evaluation.run_eval import main, run_evaluations  # noqa: F401

if __name__ == "__main__":
    main()
