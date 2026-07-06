from pydantic import BaseModel, Field


class ResumeEvaluator(BaseModel):
    resume_score: float = Field(description="Resume fitness score", ge=0.0, le=1.0)
    resume_critique: str = Field(description="Resume critique")
