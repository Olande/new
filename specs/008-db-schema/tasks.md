---
description: "Task list for Core Database Schema — all tasks completed (migrated)"
---

# Tasks: Core Database Schema

**Status**: All tasks [x] completed (migrated via 17 Alembic revisions)

## Phase 1: Foundation & Job Models

- [x] T001 Set up SQLAlchemy declarative base with `created_at` / `updated_at` mixin (`app/core/db/base.py`)
- [x] T002 Configure async session factory with PostgreSQL asyncpg driver
- [x] T003 Create `Job` model with all metadata fields, `dedup_hash` unique index
- [x] T004 Create `JobSource` model with unique `(source_name, source_job_id)` constraint
- [x] T005 Create `JobDescription` model with job_id FK
- [x] T006 Add `company_summary` text column to Job (migration `3841...`)
- [x] T007 Add `skills_text` generated column + BM25 GIN index (migration `6c50...`)

## Phase 2: User & Applications

- [x] T008 Create `User` model
- [x] T009 Create `Application` model with status, cover_letter, draft fields
- [x] T010 Create `UserJobMatch` model with relevance score
- [x] T011 Add application draft fields (migration `85e4...`)

## Phase 3: Agent & Memory

- [x] T012 Create `AgentTask` model with run_id, node tracking (migration `6486...`)
- [x] T013 Create `CareerMemory` model with entity_type enum, JSONB metadata, nullable vector
- [x] T014 Create `EntityType` and `MemoryEntityType` enums

## Phase 4: Embeddings & Vector Storage

- [x] T015 Create `Embedding` model with pgvector column, model version tracking, stale flag
- [x] T016 Configure pgvector extension for the database

## Phase 5: Alembic Infrastructure

- [x] T017 Initialize Alembic with async env (`alembic/env.py`, 64 lines)
- [x] T018 Generate and apply all 17 migrations covering schema evolution
- [x] T019 Configure `async_session` and `engine` with proper dispose handling

## Gaps Identified

| Gap | Type | Recommendation |
|-----|------|----------------|
| ❌ No model-specific tests | Test gap | Add model validation tests for constraint enforcement, cascade behavior |
| ⚠️ `skills_text` is a generated column duplicating skills array | Design | Consider whether generated column adds value vs querying ARRAY directly |
| ℹ️ No `unique` constraint on `(user_id, job_id)` in Application | Constraint | Could prevent duplicate applications; currently handled at app layer |
