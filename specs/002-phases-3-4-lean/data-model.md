# Data Model Specification

## Entities

### 1. CareerMemory (`career_memory` table)
- `id`: UUID (Primary Key)
- `user_id`: UUID (Indexed, foreign key reference to User)
- `entity_type`: Enum (`MemoryEntityType` - project, skill, achievement, education, employment_history)
- `fact_key`: VARCHAR (Default: `"default"`)
- `content`: JSONB (Store content payload)
- `valid_from`: TIMESTAMPTZ (Default: `NOW()`)
- `valid_to`: TIMESTAMPTZ (Nullable)
- `created_at`: TIMESTAMPTZ (Default: `NOW()`)

**Validation Rules**:
- `user_id` and `entity_type` are mandatory.
- Active memories have `valid_to` set to `NULL`.

### 2. Application (`applications` table)
- `id`: UUID (Primary Key)
- `user_id`: UUID (Indexed)
- `job_id`: UUID
- `status`: Enum (`draft`, `submitted`)
- `resume_draft`: TEXT (Nullable)
- `cover_letter_draft`: TEXT (Nullable)
- `notes`: TEXT (Nullable)

### 3. AgentTask (`agent_tasks` table)
- `id`: UUID (Primary Key)
- `thread_id`: VARCHAR
- `graph_name`: VARCHAR
- `status`: Enum (`pending`, `completed`, `cancelled`)
- `payload`: JSONB
