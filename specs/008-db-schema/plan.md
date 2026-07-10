# Implementation Plan: Core Database Schema

**Branch**: Multiple (iterative) | **Status**: Migrated | **Spec**: `specs/008-db-schema/spec.md`

## Summary

Design and implement the core relational schema for CareerPilot using SQLAlchemy 2.0 async ORM with PostgreSQL 16 + pgvector. The schema covers jobs, users, applications, agent tasks, memory events, and vector embeddings — evolved across 17 Alembic migrations.

## Technical Context

**Language/Version**: Python 3.13+, SQLAlchemy 2.0 async
**Storage**: PostgreSQL 16 with pgvector 0.4+
**ORM Pattern**: Declarative base with `async_session` factory
**Migrations**: Alembic 1.18+ with autogenerate
**ID Strategy**: UUID (application-generated, not DB-default)

## Schema Overview

```
Job
├── id (UUID PK)
├── dedup_hash (String, unique index)
├── title, company_name, domain_name, role, job_function
├── seniority (ARRAY), employment_type, remote_type
├── locations (ARRAY), countries (ARRAY)
├── required_skills (ARRAY), employee_count, funding
├── company_summary (Text, nullable)
├── skills_text (Text, generated — for BM25)
├── posted_at, created_at, updated_at, last_seen_at
├── status (String: active/closed)
└── relationships: sources, description, matches

JobSource
├── id (UUID PK)
├── job_id (FK → Job)
├── source_name, source_job_id, source_url
├── last_checked_at, unconfirmed_count
└── unique(source_name, source_job_id)

JobDescription
├── job_id (UUID PK, FK → Job)
├── cleaned_text (Text)
└── fetched_at

User
└── id (UUID PK), name, email, timestamps

Application
├── id (UUID PK)
├── user_id (FK → User), job_id (FK → Job)
├── status, cover_letter, draft fields
└── timestamps

UserJobMatch
├── id (UUID PK)
├── user_id (FK → User), job_id (FK → Job)
├── score (Float)
└── timestamps

AgentTask
├── id (UUID PK)
├── run_id, node_name, status, input_data, output_data
├── started_at, completed_at
└── timestamps

CareerMemory
├── id (UUID PK)
├── user_id (FK → User)
├── entity_type (Enum), entity_id
├── content (Text), metadata (JSONB)
├── embedding (Vector, nullable)
└── timestamps

Embedding
├── id (UUID PK)
├── entity_type (Enum), entity_id
├── embedding (Vector, NOT NULL)
├── model_name, model_version
├── is_stale (Boolean)
└── timestamps
```

## Migration History (17 migrations)

| Migration | Purpose |
|-----------|---------|
| `055c...` | Jobs + Users tables (initial schema) |
| `2e8e...` | Hybrid search function |
| `3841...` | Company summary column on jobs |
| `5670...` | Embedding table |
| `56b4...` | Career memory schema |
| `6413...` | Audit remediation |
| `6486...` | Agent tasks |
| `6618...` | Job descriptions |
| `6952...` | Semantic distance threshold |
| `6c50...` | skills_text generated column + BM25 index |
| `85e4...` | Application draft fields |
| `a1b2...` | Remove semantic threshold |
| `baae...` | Merge heads |
| `c558...` | Application table |
| `ce5b...` | Update hybrid search params |
| `dd5f...` | Fix timing + company |
| `f3e2...` | Update hybrid search weights |

## Key Patterns

1. **Base class** (`app/core/db/base.py`): Declarative base with `created_at` / `updated_at` mixin
2. **Async session** via `async_session` context manager in `app/core/db/base.py`
3. **pgvector** columns use `Vector(dim)` type from `pgvector.sqlalchemy`
4. **Generated column** `skills_text` combines skills array into searchable text for BM25
5. **Polymorphic embeddings**: `EntityType` enum + generic `entity_id` string for Embedding/CareerMemory
