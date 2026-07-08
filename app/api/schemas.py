from pydantic import BaseModel, ConfigDict


class DiscoverJobsResponse(BaseModel):
    pages_crawled: int
    jobs_created: int
    jobs_updated: int
    jobs_closed: int
    job_ids: list[str]


class JobSummaryResponse(BaseModel):
    id: str
    title: str
    company: str
    locations: list[str]
    role: str | None
    seniority: list[str]
    employment_type: str | None
    remote_type: str | None
    posted_at: str | None


class ListJobsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    jobs: list[JobSummaryResponse]


class JobSourceData(BaseModel):
    name: str
    url: str
    source_job_id: str


class GetJobResponse(BaseModel):
    id: str
    title: str
    company: str
    domain: str | None
    role: str | None
    job_function: str | None
    seniority: list[str]
    employment_type: str | None
    remote_type: str | None
    locations: list[str]
    countries: list[str]
    required_skills: list[str]
    employee_count: str | None
    funding: str | None
    description_preview: str | None
    posted_at: str | None
    status: str
    sources: list[JobSourceData]


class ErrorResponse(BaseModel):
    error: str


class JobSearchResult(BaseModel):
    id: str
    title: str
    company: str
    role: str | None
    locations: list[str]
    remote_type: str | None
    score: float
    skills: list[str]


class SearchJobsResponse(BaseModel):
    query: str
    results: list[JobSearchResult]


class FetchJobDescriptionResponse(BaseModel):
    job_id: str
    cleaned_text: str | None
    fetched_at: str | None


class StoreMemoryResponse(BaseModel):
    id: str
    entity_type: str
    fact_key: str
    content: dict


class MemoryData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_type: str
    fact_key: str
    content: dict
    valid_from: str | None


class GetMemoryResponse(BaseModel):
    user_id: str
    memories: list[MemoryData]


class RunWorkflowResponse(BaseModel):
    task_id: str
    thread_id: str


class GetTaskStatusResponse(BaseModel):
    id: str
    status: str
    graph_name: str
    error: str | None
    completed_at: str | None
    result: dict | None
