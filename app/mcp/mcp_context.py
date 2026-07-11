from __future__ import annotations

import contextvars
from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager

# ContextVars are task-local and async-safe — perfect for MCP request isolation
_current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_id", default=None
)
_current_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def set_request_context(*, user_id: str, tenant_id: str | None = None) -> None:
    """Called by transport layer after JWT verification. Never by LLM."""
    _current_user_id.set(user_id)
    _current_tenant_id.set(
        tenant_id or user_id
    )  # default tenant = user in single-tenant


def get_current_user_id() -> str | None:
    return _current_user_id.get()


def get_current_tenant_id() -> str | None:
    return _current_tenant_id.get()


def clear_request_context() -> None:
    _current_user_id.set(None)
    _current_tenant_id.set(None)


@contextmanager
def request_context(*, user_id: str, tenant_id: str | None = None) -> Generator[None]:
    """Sync context manager for tests / background jobs."""
    tokens = (
        _current_user_id.set(user_id),
        _current_tenant_id.set(tenant_id or user_id),
    )
    try:
        yield
    finally:
        _current_user_id.reset(tokens[0])
        _current_tenant_id.reset(tokens[1])


@asynccontextmanager
async def async_request_context(*, user_id: str, tenant_id: str | None = None):
    """Async version for ASGI handlers."""
    t1 = _current_user_id.set(user_id)
    t2 = _current_tenant_id.set(tenant_id or user_id)
    try:
        yield
    finally:
        _current_user_id.reset(t1)
        _current_tenant_id.reset(t2)


def extract_context_from_jwt(token: str) -> dict:
    """Extract claims from a JWT for request context.
    Verification is handled upstream (API Gateway); this only extracts claims.
    """
    import jwt

    token = token.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return {
            "user_id": payload.get("sub")
            or payload.get("user_id")
            or payload.get("uid"),
            "tenant_id": payload.get("tid") or payload.get("tenant_id"),
        }
    except jwt.InvalidTokenError:
        return {}
