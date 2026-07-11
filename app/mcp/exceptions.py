from __future__ import annotations


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
