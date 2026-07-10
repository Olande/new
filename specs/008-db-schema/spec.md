# Feature Specification: Core Database Schema

**Status**: Migrated (reverse-engineered from code)
**Branch**: Multiple (evolved across `main`, `dev`, `phase4-infra-decoupling`)
**Migrated**: 2026-07-10

## User Scenarios

### User Story 1 — Job & Application Data Model (Priority: P1)

Store and manage job postings, user applications, and matching data with a consistent relational schema.

**Acceptance Scenarios**:

1. **Given** a job posting is discovered, **When** normalized and persisted, **Then** it is stored with title, company, skills, location, seniority, and dedup hash
2. **Given** a user applies to a job, **When** the application is submitted, **Then** it's recorded with status, cover letter, and draft fields
3. **Given** a user-to-job relevance score is computed, **When** persisted, **Then** it's stored in `UserJobMatch` with the score value

### User Story 2 — Agent & Memory Persistence (Priority: P2)

Persist LangGraph agent tasks, career memory events, and entity embeddings for retrieval-augmented workflows.

**Acceptance Scenarios**:

1. **Given** a LangGraph agent executes a task, **When** the task completes, **Then** `AgentTask` records the workflow run_id, node, status, and timestamps
2. **Given** a career-relevant event occurs, **When** processed, **Then** `CareerMemory` stores the event type, content embedding, and metadata
3. **Given** an entity is embedded, **When** the embedding is computed, **Then** `Embedding` stores the vector, entity type, and model version

## Requirements

### Functional Requirements

- **FR-001**: System MUST store jobs with unique `dedup_hash` for deduplication
- **FR-002**: System MUST track job sources (`JobSource`) with staleness counters for each source
- **FR-003**: System MUST store full job descriptions (`JobDescription`) fetched from external APIs
- **FR-004**: System MUST support company summaries on the `Job` model (nullable text field)
- **FR-005**: System MUST store user profiles (`User`) with basic identity fields
- **FR-006**: System MUST track user job applications (`Application`) with status, cover letter, timestamps
- **FR-007**: System MUST store user-job relevance scores in `UserJobMatch`
- **FR-008**: System MUST persist LangGraph agent tasks (`AgentTask`) with run_id, node, status, timestamps
- **FR-009**: System MUST store career memory events (`CareerMemory`) with entity type, embedding, metadata
- **FR-010**: System MUST store vector embeddings (`Embedding`) with entity type, model version, pgvector column
- **FR-011**: System MUST use PostgreSQL `pgvector` extension for embedding columns

### Key Entities

- **Job**: Central entity — job posting with metadata, company summary, full-text search column
- **JobSource**: Tracks a job's origin (source name, URL, staleness count)
- **JobDescription**: Full HTML/text description fetched via Jina AI
- **User**: User profile with identification fields
- **Application**: Job application with status tracking and draft fields
- **UserJobMatch**: Relevance score between a user and a job
- **AgentTask**: LangGraph agent execution record (run_id, node, status, timestamps)
- **CareerMemory**: Stored career events with metadata and embedding
- **Embedding**: Generic vector storage (entity_type polymorphic, pgvector column)

## Success Criteria

- **SC-001**: All models have UUID primary keys
- **SC-002**: All tables use `created_at` / `updated_at` timestamp convention
- **SC-003**: Embedding columns use `pgvector` with configurable dimensions
- **SC-004**: Migrations cover creation of all 9 table types
- **SC-005**: Foreign key relationships are indexed for join performance

## Assumptions

- PostgreSQL 16 with `pgvector` extension is the only supported database
- UUIDs are generated at the application layer (not DB-default)
- Alembic handles all schema migrations (no raw SQL schema management)
