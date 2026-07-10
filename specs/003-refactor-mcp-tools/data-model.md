# Data Model Specification

No database schema changes are introduced. The refactor focuses on code isolation.

## DTO Schemas (Data Transfer Objects)

### 1. AuthenticatedUser (Domain DTO)
- `user_id`: UUID
- `tenant_id`: UUID | None

## Service DTO Mapping
- ORM entities (e.g., `Job`, `Application`) are queried in the repository layer and converted to Pydantic outputs (e.g., `JobDetailOutput`, `CreateApplicationOutput`) at the service or endpoint layer.
