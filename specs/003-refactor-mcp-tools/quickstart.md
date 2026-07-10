# Quickstart & Verification Guide

## Runnable Verification Steps

### 1. Execute Unit & Integration Tests
Ensure the refactored layer and its mock dependency injectors are fully covered:
```bash
PYTHONPATH=. pytest tests/test_mcp.py
```

### 2. Verify Stdout/Stderr and Lints
```bash
ruff check app/mcp/
```
