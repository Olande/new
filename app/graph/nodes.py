from langchain.chat_models import init_chat_model
from langgraph.graph import END
from langgraph.types import Command, Overwrite, Send

from app.core.config.settings import settings
from app.core.db.base import async_session
from app.core.jdl.schemas import JobSearchCriteria
from app.graph.graph_state import GeneratedResponse, JobScore, QAGraphState
from app.retrieval.hybrid_search import search_jobs

MAX_HEURISTIC_ATTEMPTS = 2
DEFAULT_TOP_N = 5


def get_fast_model():
    return init_chat_model(
        model="gemini-2.5-flash",
        api_key=settings.gemini_api_key,
        # extra_body={"thinking": {"type": "disabled"}},
    )


def get_frontier_model():
    return init_chat_model(
        model="gemini-3.1-flash-lite",
        api_key=settings.gemini_api_key,
        # extra_body={"thinking": {"type": "disabled"}},
    )


async def analyze_query(state: QAGraphState):
    model = get_fast_model().with_structured_output(JobSearchCriteria)
    criteria = await model.ainvoke(
        f"Extract job search criteria from this query. Only include fields "
        f"the user explicitly mentioned, never guess or enumerate options.\n\n"
        f"Query: {state.user_query}"
    )

    return {"extracted_criteria": criteria}


def build_query_text(state: QAGraphState) -> str:
    parts = [state.user_query]
    criteria = state.extracted_criteria
    if criteria:
        if criteria.skills:
            parts.append(" ".join(criteria.skills))
        if criteria.job_function:
            parts.append(criteria.job_function)
        if criteria.seniority:
            parts.append(" ".join(criteria.seniority))
        if criteria.location:
            parts.append(criteria.location)
        if criteria.remote_type:
            parts.append(criteria.remote_type)
    return " ".join(parts)


async def hybrid_search(state: QAGraphState) -> dict:
    query_text = build_query_text(state)
    limit = state.extracted_criteria.limit if state.extracted_criteria else None
    async with async_session() as db:
        results = await search_jobs(
            db=db, query_text=query_text, result_limit=limit or 20
        )
    return {"retrieved_jobs": results}


def route_to_scoring(state: QAGraphState) -> str | list[Send]:
    """
    Fan out one Send per retrieved job so each is scored independently.
    Pure routing, no LLM call: if nothing was retrieved, skip straight to
    generation (which handles the empty-results case).
    """
    if not state.retrieved_jobs:
        return "generate_draft"
    return [
        Send("score_candidate", {"user_query": state.user_query, "job_to_score": job})
        for job in state.retrieved_jobs
    ]


async def score_candidate(state: dict) -> dict:
    """Score a single job against the user's query. Runs once per Send."""
    job = state["job_to_score"]
    user_query = state["user_query"]
    model = get_fast_model().with_structured_output(JobScore)
    score = await model.ainvoke(
        f"Rate how well this job matches the user's query on a 0.0-1.0 "
        f"fit_score, with a one-sentence rationale.\n\n"
        f"User query: {user_query}\n\n"
        f"Job (job_id={job.id}): {job.title} at {job.company_name} | "
        f"skills={job.required_skills} | remote={job.remote_type} | "
        f"locations={job.locations}"
    )
    score.job_id = str(job.id)
    return {"job_scores": [score]}


def compile_results(state: QAGraphState) -> dict:
    """
    Deterministic fan-in: sort scored jobs by fit_score, keep the top N,
    and overwrite retrieved_jobs so generate_draft only sees the winners.
    job_scores is reset via Overwrite to prevent it bleeding into the next turn.
    """
    limit = (
        state.extracted_criteria.limit
        if state.extracted_criteria and state.extracted_criteria.limit
        else DEFAULT_TOP_N
    )
    jobs_by_id = {str(j.id): j for j in state.retrieved_jobs}
    ranked = sorted(state.job_scores, key=lambda s: s.fit_score, reverse=True)
    top_jobs = [jobs_by_id[s.job_id] for s in ranked[:limit] if s.job_id in jobs_by_id]

    return {
        "retrieved_jobs": top_jobs,
        "job_scores": Overwrite(value=[]),
    }


async def generate_draft(state: QAGraphState):
    if not state.retrieved_jobs:
        return {
            "draft_response": GeneratedResponse(
                insufficient_data=True,
                summary="No matching jobs were found for this query.",
                claims=[],
            )
        }
    job_context = "\n".join(
        f"job_id={j.id} | {j.title} at {j.company_name} | "
        f"skills={j.required_skills} | remote={j.remote_type} | "
        f"locations={j.locations}"
        for j in state.retrieved_jobs
    )

    prompt = (
        f"Answer the user's query using ONLY the jobs listed below. Every "
        f"claim must cite the exact job_id it came from. If these jobs don't "
        f"actually answer the query, set insufficient_data=True instead of "
        f"guessing.\n\n"
        f"User query: {state.user_query}\n\n"
        f"Retrieved jobs:\n{job_context}"
    )
    if state.grounding_error:
        prompt += (
            f"\n\nYour previous answer cited job_id(s) not present in the "
            f"list above ({state.grounding_error}). Only cite job_ids that "
            f"appear in the retrieved jobs."
        )

    model = get_frontier_model().with_structured_output(GeneratedResponse)
    response = await model.ainvoke(prompt)
    return {"draft_response": response, "grounding_error": None}


def find_ungrounded_claims(state: QAGraphState) -> list[str]:
    """Return the job_ids cited in the draft that aren't in retrieved_jobs."""
    valid_ids = {str(j.id) for j in state.retrieved_jobs}
    return [c.job_id for c in state.draft_response.claims if c.job_id not in valid_ids]


async def heuristic_check(state: QAGraphState) -> Command:
    if state.draft_response.insufficient_data:
        return Command(goto=END)

    bad_ids = find_ungrounded_claims(state)
    if not bad_ids:
        return Command(goto=END)

    attempts = state.heuristic_attempts + 1
    if attempts >= MAX_HEURISTIC_ATTEMPTS:
        fallback = GeneratedResponse(
            insufficient_data=True,
            summary="We couldn't produce a fully grounded answer for this query.",
            claims=[],
        )
        return Command(
            goto=END,
            update={"draft_response": fallback, "heuristic_attempts": attempts},
        )

    return Command(
        goto="generate_draft",
        update={
            "heuristic_attempts": attempts,
            "grounding_error": ", ".join(bad_ids),
        },
    )
