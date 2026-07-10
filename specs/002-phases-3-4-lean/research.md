# Research Report: Phases 3-4 Lean Re-Implementation

## Technical Decisions

### 1. Checkpointer & Store Library Choice
- **Decision**: Use `langgraph-checkpoint-postgres` and `langgraph-store-postgres` for thread state and memory.
- **Rationale**: Replaces in-memory savers to ensure multi-node horizontal scalability and long-term state preservation.
- **Alternatives Considered**: Redis checkpointer (ruled out because Postgres is already running in production and supports standard vector embeddings via `pgvector` seamlessly).

### 2. Store Mapping Scheme
- **Decision**: Map `CareerMemory` records to the Postgres `Store` using the namespace `(str(user_id), entity_type.value)`.
- **Rationale**: Isolates user facts by type and ensures quick querying via the `asearch` and `aput` Store API.
- **Alternatives Considered**: Storing as one monolithic list (rejected because searching becomes expensive).

### 3. Tenant Isolation Strategy
- **Decision**: Context variables (`ContextVar`) inside Starlette HTTP middleware to verify JWT tokens and inject user IDs task-safely.
- **Rationale**: Ensures no query is executed without filtering by the verified tenant.
