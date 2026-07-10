from __future__ import annotations

import base64
import contextvars
import json
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
    """
    Lean JWT extraction without reinventing verification.
    Uses PyJWT if available, else manual base64 decode of payload.
    Verification should happen at edge (API Gateway); this only extracts claims.
    """
    token = token.removeprefix("Bearer ").strip()
    try:
        import jwt  # type: ignore

        # verify=False for extraction only — real verification is done upstream
        payload = jwt.decode(token, options={"verify_signature": False})
        return {
            "user_id": payload.get("sub")
            or payload.get("user_id")
            or payload.get("uid"),
            "tenant_id": payload.get("tid") or payload.get("tenant_id"),
        }
    except Exception:
        pass

    # Fallback: manual base64 payload decode (no verification)
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload_b64))
            return {
                "user_id": data.get("sub") or data.get("user_id"),
                "tenant_id": data.get("tid") or data.get("tenant_id"),
            }
    except Exception:
        pass

    return {}
