import uuid
from datetime import datetime

from sqlalchemy import Computed, DateTime, String, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dedup_hash: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    domain_name: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    job_function: Mapped[str | None] = mapped_column(String, nullable=True)
    seniority: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default="{}", nullable=False
    )
    employment_type: Mapped[str | None] = mapped_column(String, nullable=True)
    remote_type: Mapped[str | None] = mapped_column(String, nullable=True)
    locations: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default="{}", nullable=False
    )
    countries: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default="{}", nullable=False
    )
    required_skills: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default="{}", nullable=False
    )
    skills_text: Mapped[str] = mapped_column(
        String,
        Computed("immutable_array_to_string(required_skills, ' ')", persisted=True),
        nullable=False,
    )
    employee_count: Mapped[str | None] = mapped_column(String, nullable=True)
    funding: Mapped[str | None] = mapped_column(String, nullable=True)
    company_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, server_default="active", nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
