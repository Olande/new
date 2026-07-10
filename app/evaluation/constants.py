"""Shared constants for the evaluation package."""

# Query styles written into LangSmith example metadata by seed_eval_datasets.py
MATCHING_STYLES: frozenset[str] = frozenset({"exact_terms", "paraphrase", "distractor"})
NO_MATCH_STYLE: str = "no_match"
