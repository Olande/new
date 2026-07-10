from dataclasses import asdict, dataclass

# LangSmith dataset produced by scripts/seed_eval_datasets.py
RETRIEVAL_DATASET = "careerpilot-matching-eval-v2"

# Relative drop vs prior experiment that fails CI
NDCG_REGRESSION_THRESHOLD = 0.05
MRR_REGRESSION_THRESHOLD = 0.05

# Query styles stored in example metadata by the seeder
MATCHING_STYLES = frozenset({"exact_terms", "paraphrase", "distractor"})
NO_MATCH_STYLE = "no_match"


@dataclass(frozen=True, slots=True)
class SearchParams:
    """Hybrid search knobs used for both production defaults and eval sweeps."""

    bm25_weight: float = 0.1
    vector_weight: float = 0.9
    cosine_distance_threshold: float = 0.5
    result_limit: int = 20

    def as_dict(self) -> dict:
        return asdict(self)


# Align with app.retrieval.hybrid_search.search_jobs defaults
DEFAULT_SEARCH_PARAMS = SearchParams()
