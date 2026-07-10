# MCP Contract Interface Mapping

## Tool Endpoints & Services

### 1. `JobService.search_jobs`
- **Arguments**: `query: str, limit: int, cosine_threshold: float`
- **Returns**: `SearchJobsOutput`

### 2. `JobService.get_job`
- **Arguments**: `job_id: UUID`
- **Returns**: `JobDetailOutput`

### 3. `ProfileService.get_profile`
- **Arguments**: `user: AuthenticatedUser`
- **Returns**: `GetProfileOutput`

### 4. `ApplicationService.create_draft`
- **Arguments**: `user: AuthenticatedUser, job_id: UUID, resume_draft: str | None, cover_letter_draft: str | None, notes: str | None`
- **Returns**: `CreateApplicationOutput`
