# Feature Specification: Hybrid Search

**Status**: Migrated (reverse-engineered from code)
**Branch**: Multiple (evolved across `dev`, `phase4-infra-decoupling`)
**Migrated**: 2026-07-10

## User Scenarios

### User Story 1 — Hybrid Job Search (Priority: P1)

Users search for jobs using natural language queries. Results combine BM25 full-text search on skills with vector cosine similarity on job embeddings, fused via Reciprocal Rank Fusion (RRF).

**Acceptance Scenarios**:

1. **Given** jobs with embeddings in the database, **When** a user searches with a natural language query, **Then** results are ranked by RRF score combining BM25 and vector similarity
2. **Given** a search query, **When** the query has no skill matches but strong semantic matches, **Then** vector similarity compensates for missing keyword overlap
3. **Given** search parameters, **When** `cosine_distance_threshold` is exceeded for all candidates, **Then** only results below the threshold are returned

### User Story 2 — Configurable Scoring Weights (Priority: P2)

The search algorithm supports tunable weights for BM25 vs vector contribution, optimized via hyperparameter search.

**Acceptance Scenarios**:

1. **Given** a search query, **When** `bm25_weight` is 0.0, **Then** results are purely vector-based
2. **Given** a search query, **When** `vector_weight` is 0.0, **Then** results are purely BM25-based
3. **Given** both weights are non-zero, **Then** scores are normalized via RRF before fusion

## Requirements

### Functional Requirements

- **FR-001**: System MUST support BM25 full-text search on `skills_text` column using pg_bigm or equivalent
- **FR-002**: System MUST support cosine similarity search on `Embedding.vector` column using pgvector
- **FR-003**: System MUST fuse BM25 and vector results using Reciprocal Rank Fusion (RRF)
- **FR-004**: System MUST support configurable RRF constant (currently `k = 60`)
- **FR-005**: System MUST support configurable `cosine_distance_threshold` (default 0.4513)
- **FR-006**: System MUST support configurable `bm25_weight` (default 0.2069) and `vector_weight` (default 0.7931)
- **FR-007**: System MUST limit results (default 20) with optional override up to 50
- **FR-008**: System MUST only search active jobs (`status = 'active'`)
- **FR-009**: System MUST return `rrf_score` as the combined relevance score
- **FR-010**: System MUST embed the query text using the same embedding model as job embeddings

### Key Entities

- **hybrid_search_jobs()**: PostgreSQL function that performs the fused search
- **skills_text**: Generated column on `jobs` table for BM25 indexing
- **Embedding**: pgvector storage with `entity_type = 'job'` for job descriptions
- **RRF Score**: Combined rank using `bm25_weight * (1/(60+bm25_rank)) + vector_weight * (1/(60+vector_rank))`

## Success Criteria

- **SC-001**: 10 sample queries return hybrid results within 500ms
- **SC-002**: BM25-only mode (`vector_weight=0`) returns valid results
- **SC-003**: Vector-only mode (`bm25_weight=0`) returns valid results
- **SC-004**: RRF scoring produces scores in range (0, bm25_weight + vector_weight)
- **SC-005**: Empty query results return empty list (no crash)

## Assumptions

- PostgreSQL has the `pg_bm25` extension (or equivalent `pg_bigm`) for BM25 scoring
- Embeddings are pre-computed and stored in the `Embedding` table with `entity_type = 'job'`
- The RRF constant `k=60` provides reasonable score distribution for expected result set sizes
