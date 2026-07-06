import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class JobSearchCriteria(BaseModel):
    model_config = {"populate_by_name": True}
    skills: list[str] | None = Field(default=None, alias="q")
    location: str | None = None
    remote_type: str | None = None
    job_function: str | None = None
    seniority: list[str] | None = None


class JobSourceCreate(BaseModel):
    source_name: str
    source_job_id: str
    source_url: str
    first_seen_at: datetime


class JobCreate(BaseModel):
    title: str
    company_name: str
    domain_name: str | None = None
    role: str | None = None
    job_function: str | None = None
    seniority: list[str] = Field(default_factory=list)
    employment_type: str | None = None
    remote_type: str | None = None
    locations: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    employee_count: str | None = None
    funding: str | None = None
    posted_at: datetime | None = None
    dedup_hash: str
    status: str = "active"
    source: JobSourceCreate


class JobRead(BaseModel):
    """Plain read model for jobs on the blackboard"""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str
    company_name: str
    domain_name: str | None = None
    role: str | None = None
    job_function: str | None = None
    seniority: list[str] = Field(default_factory=list)
    employment_type: str | None = None
    remote_type: str | None = None
    locations: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    employee_count: str | None = None
    funding: str | None = None
    posted_at: datetime | None = None
    dedup_hash: str
    status: str = "active"


class JobCandidate(BaseModel):
    job: JobRead
    score: float


class JobEmbeddingDocument(BaseModel):
    title: str | None = None
    company: str | None = None
    role: str | None = None
    function: str | None = None
    seniority: list[str] = []
    employment: str | None = None
    remote: str | None = None
    locations: list[str] = []
    skills: list[str] = []
    description: str | None = None
