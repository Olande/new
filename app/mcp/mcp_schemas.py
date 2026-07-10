"""
Pydantic schemas for MCP tools. Strict validation = no hallucinated args.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class SearchJobsInput(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Natural language job search query",
    )
    limit: int = Field(default=10, ge=1, le=20, description="Max results")
    cosine_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class JobHit(BaseModel):
    id: str
    title: str
    company_name: str
    required_skills: list[str] = []
    remote_type: str | None = None
    locations: list[str] = []
    score: float
    fallback_source: str | None = None  # "jdl_api" or None

    @classmethod
    def from_job(cls, job, score: float = 0.0) -> JobHit:
        return cls(
            id=str(job.id),
            title=job.title,
            company_name=job.company_name,
            required_skills=list(job.required_skills or []),
            remote_type=job.remote_type,
            locations=list(job.locations or []),
            score=score,
            fallback_source=getattr(job, "fallback_source", None),
        )


class SearchJobsOutput(BaseModel):
    hits: list[JobHit]
    total: int
    fallback_used: bool = False
    dropped_count: int = 0


class GetJobInput(BaseModel):
    job_id: UUID = Field(..., description="Job UUID from search results")


class JobDetailOutput(BaseModel):
    id: str
    title: str
    company_name: str
    description: str = ""
    required_skills: list[str] = []
    locations: list[str] = []
    remote_type: str | None = None
    employment_type: str | None = None
    seniority: list[str] = []
    fallback_source: str | None = None  # "jdl_api" or None

    @classmethod
    def from_job(cls, job, description: str = "") -> JobDetailOutput:
        return cls(
            id=str(job.id),
            title=job.title,
            company_name=job.company_name,
            description=description,
            required_skills=list(job.required_skills or []),
            locations=list(job.locations or []),
            remote_type=job.remote_type,
            employment_type=job.employment_type,
            seniority=list(job.seniority or []),
            fallback_source=getattr(job, "fallback_source", None),
        )


class GetProfileOutput(BaseModel):
    user_id: str
    email: str
    career_memories: list[dict] = []


class CreateApplicationInput(BaseModel):
    job_id: UUID
    resume_draft: str | None = Field(default=None, max_length=20000)
    cover_letter_draft: str | None = Field(default=None, max_length=20000)
    notes: str | None = Field(default=None, max_length=2000)


class CreateApplicationOutput(BaseModel):
    application_id: str
    job_id: str
    status: str = "draft"


class ErrorResponse(BaseModel):
    error: bool = True
    message: str
    code: str = "tool_error"


class SubmitApplicationInput(BaseModel):
    job_id: UUID = Field(..., description="Job to submit")
    application_id: UUID | None = Field(default=None)


class SubmitApplicationOutput(BaseModel):
    needs_approval: bool = True
    task_id: str
    job_id: str
    application_id: str
    preview: dict = Field(default_factory=dict)
    message: str = "Human approval required"


class ConfirmSubmissionInput(BaseModel):
    task_id: UUID
    approved: bool


class ConfirmSubmissionOutput(BaseModel):
    status: str
    application_id: str
    job_id: str
    message: str
