from __future__ import annotations

import logging
from functools import wraps

from app.mcp.mcp_schemas import ErrorResponse

logger = logging.getLogger("mcp")


class DomainException(Exception):  # noqa: N818
    """Base exception for all domain logic errors."""
    def __init__(self, message: str, code: str = "domain_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(DomainException):
    """Raised when a requested resource is not found."""
    def __init__(self, message: str):
        super().__init__(message, "not_found")


class UnauthorizedError(DomainException):
    """Raised when an operation is unauthorized or tenant check fails."""
    def __init__(self, message: str):
        super().__init__(message, "unauthorized")


class ValidationError(DomainException):
    """Raised when input parameters fail validation."""
    def __init__(self, message: str):
        super().__init__(message, "validation_error")


def translate_mcp_exceptions(func):
    """Decorator to catch domain exceptions and convert them to standard ErrorResponses."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except DomainException as e:
            return ErrorResponse(error=True, message=e.message, code=e.code).model_dump()
        except PermissionError as e:
            return ErrorResponse(error=True, message=str(e), code="unauthorized").model_dump()
        except ValueError as e:
            return ErrorResponse(error=True, message=str(e), code="validation_error").model_dump()
        except Exception as e:
            logger.exception(f"Unhandled error in {func.__name__}")
            return ErrorResponse(error=True, message=str(e), code="internal_error").model_dump()
    return wrapper
