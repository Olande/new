from pydantic import BaseModel, Field

from app.core.jdl.schemas import JobSearchCriteria, JobSearchResult


class JobClaim(BaseModel):
    text: str = Field(description="The claim being made, in natural language.")
    job_id: str = Field(description="The id of the job this claim is grounded in.")


class GeneratedResponse(BaseModel):
    insufficient_data: bool = Field(
        description="True if the retrieved jobs do not contain enough information to answer the user's query."
    )
    summary: str = Field(description="A natural language answer to the user's query.")
    claims: list[JobClaim] = Field(
        default_factory=list,
        description="Every factual claim in the summary, each citing its source job_id.",
    )


class QAGraphState(BaseModel):
    user_query: str
    extracted_criteria: JobSearchCriteria | None = None
    retrieved_jobs: list[JobSearchResult] = Field(default_factory=list)
    draft_response: GeneratedResponse | None = None
