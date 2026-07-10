from __future__ import annotations

from langchain.chat_models import init_chat_model
from langgraph.graph import END
from langgraph.types import Command, Overwrite

from app.core.config.settings import settings
from app.graph.graph_state import (
    CritiqueResult,
    GeneratedResponse,
    JobScore,
    QAGraphState,
)

MAX_HEURISTIC_ATTEMPTS = 2
MAX_VERIFICATION_ATTEMPTS = 2
DEFAULT_TOP_N = 5


def get_fast_model():
    return init_chat_model(model="gemini-2.5-flash", api_key=settings.gemini_api_key)


def get_frontier_model():
    return init_chat_model(
        model="gemini-3.1-flash-lite", api_key=settings.gemini_api_key
    )


async def score_candidate(state: dict) -> dict:
    job = state["job_to_score"]
    user_query = state["user_query"]
    model = get_fast_model().with_structured_output(JobScore)
    score = await model.ainvoke(
        f"Rate fit 0.0-1.0 with one-sentence rationale.\nUser: {user_query}\nJob {job.id}: {job.title} at {job.company_name} skills={job.required_skills} remote={job.remote_type} loc={job.locations}"
    )
    score.job_id = str(job.id)
    return {"job_scores": [score]}


def compile_results(state: QAGraphState) -> dict:
    limit = (
        state.extracted_criteria.limit
        if state.extracted_criteria and state.extracted_criteria.limit
        else DEFAULT_TOP_N
    )
    jobs_by_id = {str(j.id): j for j in state.retrieved_jobs}
    ranked = sorted(state.job_scores, key=lambda s: s.fit_score, reverse=True)
    top = [jobs_by_id[s.job_id] for s in ranked[:limit] if s.job_id in jobs_by_id]
    return {"retrieved_jobs": top, "job_scores": Overwrite(value=[])}


async def generate_draft(state: QAGraphState):
    if not state.retrieved_jobs:
        return {
            "draft_response": GeneratedResponse(
                insufficient_data=True, summary="No matching jobs found.", claims=[]
            )
        }
    ctx = "\n".join(
        f"job_id={j.id} | {j.title} at {j.company_name} | skills={j.required_skills} | remote={j.remote_type} | loc={j.locations}"
        for j in state.retrieved_jobs
    )
    prompt = (
        f"Answer using ONLY jobs below. Every claim must cite exact job_id. If jobs don't answer query, set insufficient_data=True.\n"
        f"User query: {state.user_query}\nRetrieved:\n{ctx}"
    )
    if state.grounding_error:
        prompt += f"\n\nPrevious answer cited invalid job_ids ({state.grounding_error}). Only cite IDs in retrieved list."
    if state.critique_feedback:
        prompt += f"\n\nCritic feedback: {state.critique_feedback}. Fix to be faithful."
    model = get_frontier_model().with_structured_output(GeneratedResponse)
    resp = await model.ainvoke(prompt)
    return {"draft_response": resp, "grounding_error": None, "critique_feedback": None}


def find_ungrounded_claims(state: QAGraphState) -> list[str]:
    valid = {str(j.id) for j in state.retrieved_jobs}
    if not state.draft_response:
        return []
    return [c.job_id for c in state.draft_response.claims if c.job_id not in valid]


async def heuristic_check(state: QAGraphState) -> Command:
    if state.draft_response and state.draft_response.insufficient_data:
        return Command(goto=END)
    bad = find_ungrounded_claims(state)
    if not bad:
        return Command(goto="llm_critic")
    attempts = state.heuristic_attempts + 1
    if attempts >= MAX_HEURISTIC_ATTEMPTS:
        fb = GeneratedResponse(
            insufficient_data=True,
            summary="Couldn't produce grounded answer.",
            claims=[],
        )
        return Command(
            goto=END, update={"draft_response": fb, "heuristic_attempts": attempts}
        )
    return Command(
        goto="generate_draft",
        update={"heuristic_attempts": attempts, "grounding_error": ", ".join(bad)},
    )


async def llm_critic(state: QAGraphState) -> Command:
    if not state.draft_response or state.draft_response.insufficient_data:
        return Command(goto=END)
    ctx = "\n".join(
        f"{j.id} | {j.title} at {j.company_name} | {j.required_skills}"
        for j in state.retrieved_jobs
    )
    prompt = (
        f"Strict faithfulness critic. Check draft against retrieved jobs. Flag invented salaries, locations, skills.\n"
        f"User: {state.user_query}\nJobs:\n{ctx}\nDraft: {state.draft_response.summary}\nClaims: {[f'{c.job_id}:{c.text}' for c in state.draft_response.claims]}"
    )
    model = get_frontier_model().with_structured_output(CritiqueResult)
    try:
        crit = await model.ainvoke(prompt)
    except Exception:
        return Command(goto=END)
    if crit.is_valid:
        return Command(
            goto=END, update={"verification_attempts": 0, "critique_feedback": None}
        )
    attempts = state.verification_attempts + 1
    if attempts >= MAX_VERIFICATION_ATTEMPTS:
        fb = GeneratedResponse(
            insufficient_data=True,
            summary="Failed verification after retries.",
            claims=[],
        )
        return Command(
            goto=END, update={"draft_response": fb, "verification_attempts": attempts}
        )
    fb = "; ".join(crit.issues) if crit.issues else "Semantic mismatch"
    if crit.suggested_fix:
        fb += f" | Fix: {crit.suggested_fix}"
    return Command(
        goto="generate_draft",
        update={"verification_attempts": attempts, "critique_feedback": fb},
    )
