from langchain.chat_models import init_chat_model

from app.core.config.settings import settings
from app.core.db.base import async_session
from app.core.jdl.schemas import JobSearchCriteria
from app.graph.graph_state import GeneratedResponse, QAGraphState
from app.retrieval.hybrid_search import search_jobs


def get_fast_model():
    return init_chat_model(
        model="deepseek-v4-flash",
        api_key=settings.deepseek_api_key,
        extra_body={"thinking": {"type": "disabled"}},
    )


def get_frontier_model():
    return init_chat_model(
        model="deepseek-v4-pro",
        api_key=settings.deepseek_api_key,
        extra_body={"thinking": {"type": "disabled"}},
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

    model = get_frontier_model().with_structured_output(GeneratedResponse)
    response = await model.ainvoke(
        f"Answer the user's query using ONLY the jobs listed below. Every "
        f"claim must cite the exact job_id it came from. If these jobs don't "
        f"actually answer the query, set insufficient_data=True instead of "
        f"guessing.\n\n"
        f"User query: {state.user_query}\n\n"
        f"Retrieved jobs:\n{job_context}"
    )
    return {"draft_response": response}
