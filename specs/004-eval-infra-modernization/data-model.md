# Data Model & Configurations: Evaluation Infrastructure Modernization

## Database Entities
* **No Database Model Changes**: This refactor does not add, remove, or modify any database schemas or SQLAlchemy models. All jobs and search candidate data remain mapped to `JobDescription` and `JobSearchResult`.

## Runtime Configurations
We maintain the parameters used to control hybrid search evaluations.

### SearchParams
A dataclass mapped to search execution configs.

| Attribute | Type | Constraints | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `bm25_weight` | `float` | `0.0 <= weight <= 1.0` | `0.1` | BM25 retrieval weight. |
| `vector_weight` | `float` | `0.0 <= weight <= 1.0` | `0.9` | Vector semantic search weight. |
| `cosine_distance_threshold` | `float` | `0.0 <= threshold <= 1.0` | `0.5` | Threshold for vector similarity filter. |
| `result_limit` | `int` | `limit > 0` | `20` | Maximum candidates to return. |
