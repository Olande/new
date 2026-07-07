import uuid
from typing import Any, TypeVar

from sqlalchemy import Select

T = TypeVar("T")


def apply_tenant_scope(stmt: Select, model: Any, user_id: uuid.UUID) -> Select:
    """
    Applies row-level tenant isolation to a SQLAlchemy select statement.
    Ensures that queries strictly scope results to the given user_id.
    """
    if hasattr(model, "user_id"):
        return stmt.where(model.user_id == user_id)
    raise ValueError(
        f"Model {model} does not have a user_id column for tenant isolation."
    )
