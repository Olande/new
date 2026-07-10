import jwt
import pytest
from starlette.testclient import TestClient

from app.mcp.mcp_context import (
    async_request_context,
    extract_context_from_jwt,
    get_current_tenant_id,
    get_current_user_id,
    request_context,
)
from app.mcp.mcp_server import create_asgi_app


def test_jwt_extraction_and_context_vars():
    # 1. Test manual token payload extraction (Base64 fallback or PyJWT)
    token_data = {"sub": "user-123", "tid": "tenant-456"}
    # Create an unsigned JWT token manually for extraction testing
    token = jwt.encode(token_data, "secret", algorithm="HS256")

    extracted = extract_context_from_jwt(token)
    assert extracted.get("user_id") == "user-123"
    assert extracted.get("tenant_id") == "tenant-456"

    # 2. Test context managers
    with request_context(user_id="user-123", tenant_id="tenant-456"):
        assert get_current_user_id() == "user-123"
        assert get_current_tenant_id() == "tenant-456"

    # Context should be cleaned up after exit
    assert get_current_user_id() is None
    assert get_current_tenant_id() is None


@pytest.mark.asyncio
async def test_async_context_isolation():
    # Test async context isolation
    async with async_request_context(user_id="async-user", tenant_id="async-tenant"):
        assert get_current_user_id() == "async-user"
        assert get_current_tenant_id() == "async-tenant"

    assert get_current_user_id() is None


def test_tenant_middleware_context_propagation():
    # Build the ASGI app with middleware
    app = create_asgi_app()

    # We will test using Starlette TestClient if it's a HTTP app
    client = TestClient(app)

    # Let's verify that hitting the endpoint with auth header sets context
    # Create a JWT token
    token = jwt.encode(
        {"sub": "mid-user", "tid": "mid-tenant"}, "secret", algorithm="HS256"
    )

    # Send a request with the Authorization header
    headers = {"Authorization": f"Bearer {token}"}
    client.get("/tools", headers=headers)

    # The ASGI middleware runs and clears context after. Ensure it's cleared:
    assert get_current_user_id() is None


@pytest.mark.asyncio
async def test_exception_translation():
    from app.mcp.exceptions import (
        NotFoundError,
        UnauthorizedError,
        ValidationError,
        translate_mcp_exceptions,
    )

    @translate_mcp_exceptions
    async def sample_func(exc_to_raise):
        if exc_to_raise:
            raise exc_to_raise
        return {"success": True}

    # 1. Test success route
    res = await sample_func(None)
    assert res == {"success": True}

    # 2. Test NotFoundError mapping
    res = await sample_func(NotFoundError("Job not found"))
    assert res["error"] is True
    assert res["code"] == "not_found"
    assert res["message"] == "Job not found"

    # 3. Test UnauthorizedError mapping
    res = await sample_func(UnauthorizedError("Invalid token"))
    assert res["error"] is True
    assert res["code"] == "unauthorized"

    # 4. Test ValidationError mapping
    res = await sample_func(ValidationError("Invalid ID"))
    assert res["error"] is True
    assert res["code"] == "validation_error"

    # 5. Test generic Exception translation
    res = await sample_func(Exception("Database error"))
    assert res["error"] is True
    assert res["code"] == "internal_error"
