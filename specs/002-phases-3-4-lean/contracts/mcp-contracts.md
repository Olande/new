# MCP Interface Contracts

## Public API schemas

### 1. `search_jobs_tool`
- **Input**:
  - `query` (str, required)
  - `limit` (int, default: 10)
  - `cosine_threshold` (float, default: 0.5)
- **Output**:
  - `hits` (list[JobHit])
  - `total` (int)

### 2. `submit_application_tool`
- **Input**:
  - `job_id` (str, required)
  - `application_id` (str, optional)
- **Output**:
  - `needs_approval` (bool)
  - `task_id` (str)
  - `preview` (dict)

### 3. `confirm_submission_tool`
- **Input**:
  - `task_id` (str, required)
  - `approved` (bool, required)
- **Output**:
  - `status` (str)
  - `application_id` (str)
  - `job_id` (str)
  - `message` (str)
