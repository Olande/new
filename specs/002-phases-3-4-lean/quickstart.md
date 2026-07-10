# Quickstart & Validation Guide

## Runnable Verification Scenarios

### 1. Test Postgres Checkpointer Connection
Start the local server instance with Postgres connection strings and verify that the migrations are automatically executed:
```bash
PYTHONPATH=app/mcp python -m app.mcp.mcp_server
```

### 2. Verify HIL Submission Workflow
Use the MCP tool client to execute application draft submission:
1. Call `search_jobs_tool` to get a list of active job IDs.
2. Call `submit_application_tool` with the selected job ID. This will trigger a human-in-the-loop validation request and register a pending task ID.
3. Call `confirm_submission_tool` with the returned task ID and `approved: true` to finalize database updates.
