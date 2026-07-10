# Feature Specification: LLM Embeddings

**Status**: Migrated (reverse-engineered from code)
**Branch**: Multiple (evolved across `dev`, `phase4-infra-decoupling`)
**Migrated**: 2026-07-10

## User Scenarios

### User Story 1 — Deterministic Job Embedding Generation (Priority: P1)

Job embeddings are generated automatically after discovery using Google's Gemini Embedding model, with stale detection and refresh.

**Acceptance Scenarios**:

1. **Given** a newly discovered job, **When** the discovery cycle completes, **Then** a 1024-dimensional embedding is generated and stored
2. **Given** a job whose metadata (title, skills, description) has changed, **When** the next refresh cycle runs, **Then** the embedding is regenerated
3. **Given** an embedding older than 7 days (`valid_until`), **When** the refresh cycle runs, **Then** the embedding is regenerated

### User Story 2 — Batched, Resilient Embedding API Calls (Priority: P2)

Embedding API calls are batched for throughput with retry and concurrency control.

**Acceptance Scenarios**:

1. **Given** 25 jobs needing embeddings, **When** processed, **Then** they are split into 3 batches of 10/10/5
2. **Given** a rate-limited API response (429), **When** the batch is retried, **Then** exponential backoff is applied (5 attempts max)
3. **Given** multiple batches, **When** processed concurrently, **Then** at most 3 batches run in parallel

### User Story 3 — Embedding Integrity via Content Hashing (Priority: P3)

Each embedding stores a SHA-256 hash of its input text to detect staleness without re-embedding.

**Acceptance Scenarios**:

1. **Given** a job with unchanged metadata, **When** `compute_job_embedding_hash()` is called, **Then** it produces the same hash as the stored `embedding_input_hash`
2. **Given** a job with unchanged hash and valid `valid_until`, **When** the refresh cycle runs, **Then** the embedding is skipped (no API call)

## Requirements

### Functional Requirements

- **FR-001**: System MUST generate 1024-dimensional embeddings using `gemini-embedding-2` model
- **FR-002**: System MUST construct embedding text from job title, company, skills, description, summary
- **FR-003**: System MUST batch embedding API calls (batch size: 10)
- **FR-004**: System MUST limit concurrent API calls (max: 3)
- **FR-005**: System MUST retry on `ResourceExhausted` (429) and `ServiceUnavailable` (503) with jitter (5 attempts)
- **FR-006**: System MUST compute SHA-256 hash of embedding input for staleness detection
- **FR-007**: System MUST set `valid_until` to 7 days from creation
- **FR-008**: System MUST skip re-embedding if hash matches and embedding is valid
- **FR-009**: System MUST support versioned embedding text format (`EMBEDDING_TEXT_VERSION`)
- **FR-010**: System MUST store model name (`gemini-embedding-2`) with each embedding for traceability

### Key Entities

- **GoogleGenerativeAIEmbeddings**: LangChain wrapper for Gemini embedding API
- **Embedding**: pgvector table row storing vector, hash, model info, validity window
- **JobEmbeddingDocument**: Pydantic model structuring the embedding input text
- **embedding_input_hash**: SHA-256 of versioned input text for change detection

## Success Criteria

- **SC-001**: A full refresh of 100 active jobs completes within 60 seconds
- **SC-002**: Zero unnecessary API calls for jobs with unchanged metadata and valid embeddings
- **SC-003**: All embedding API errors are retried up to 5 times before failing
- **SC-004**: Embedding text version bumps trigger full re-embedding (hash mismatch)

## Assumptions

- Google Gemini Embedding API key is configured via `GOOGLE_API_KEY` environment variable
- The `gemini-embedding-2` model supports 1024-dimensional output
- Embedding text constructed from job fields is sufficient for semantic search quality
- 7-day validity window balances freshness against API cost
