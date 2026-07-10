from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langgraph.graph import END
from langgraph.types import Command, Overwrite, Send

from app.core.config.settings import settings
from app.core.db.base import async_session
from app.core.jdl.schemas import JobSearchCriteria
from app.graph.graph_state import (
    CritiqueResult,
    GeneratedResponse,
    JobScore,
    QAGraphState,
)
from app.retrieval.hybrid_search import search_jobs

MAX_HEURISTIC_ATTEMPTS = 2
MAX_VERIFICATION_ATTEMPTS = 2
DEFAULT_TOP_N = 5


def get_fast_model():
    return init_chat_model(model="gemini-2.5-flash", api_key=settings.gemini_api_key)


def get_frontier_model():
    return init_chat_model(model="gemini-3.1-flash-lite", api_key=settings.gemini_api_key)


# ---------- Store <-> CareerMemory bridge ----------
# CareerMemory table is the legacy source of truth. New code uses Postgres Store
# with namespace = (user_id, entity_type) where entity_type in
# {project, skill, achievement, education, employment_history}
# This helper keeps both in sync and is lean: stdlib + store API only.

async def load_career_memories_from_store(store: Any, user_id: str, limit_per_type: int = 3) -> str:
    """Read cross-thread memories from Postgres Store. Returns snippet for prompt augmentation."""
    if not store or not user_id:
        return ""
    snippets: list[str] = []
    entity_types = ["skill", "project", "achievement", "employment_history", "education"]
    for et in entity_types:
        try:
            if hasattr(store, "asearch"):
                # PostgresStore asearch(namespace, limit)
                results = await store.asearch((user_id, et), limit=limit_per_type)
                for r in results:
                    # r.value is dict like {"text": "..."} or raw content dict
                    val = r.value if isinstance(r.value, dict) else {"text": str(r.value)}
                    txt = val.get("text") or val.get("content") or str(val)[:120]
                    snippets.append(f"{et}:{txt}")
            elif hasattr(store, "aget"):
                item = await store.aget((user_id, et), "default")
                if item:
                    snippets.append(f"{et}:{str(item.value)[:120]}")
        except Exception:
            continue
    if snippets:
        return "\nUser career memory (from Postgres Store, migrated from career_memory table): " + "; ".join(snippets[:6])
    return ""


async def migrate_career_memory_table_to_store(db_session, store: Any, user_id: str) -> int:
    """
    One-time migration helper: copies rows from career_memory table into Postgres Store.
    Uses same namespace scheme so new code can read via Store API.
    Lean: uses SQLAlchemy + store.aput, no custom ORM.
    """
    if not store:
        return 0
    try:
        import uuid

        from sqlalchemy import select

        from app.core.db.models.memory import CareerMemory

        uid = uuid.UUID(user_id)
        q = await db_session.execute(
            select(CareerMemory)
            .where(CareerMemory.user_id == uid, CareerMemory.valid_to.is_(None))
            .limit(50)
        )
        rows = q.scalars().all()
        count = 0
        for row in rows:
            ns = (user_id, row.entity_type.value if hasattr(row.entity_type, "value") else str(row.entity_type))
            key = row.fact_key or "default"
            value = row.content if isinstance(row.content, dict) else {"text": str(row.content)}
            try:
                if hasattr(store, "aput"):
                    await store.aput(ns, key, value)
                    count += 1
            except Exception:
                continue
        return count
    except Exception:
        return 0


# ---------- Nodes ----------

async def analyze_query(state: QAGraphState, *, store: Any | None = None):
    user_snippet = ""
    if store and state.user_id:
        try:
            user_snippet = await load_career_memories_from_store(store, state.user_id)
        except Exception:
            user_snippet = ""

    model = get_fast_model().with_structured_output(JobSearchCriteria)
    prompt = (
        "Extract job search criteria from query. Only include fields explicitly mentioned, never guess.\n"
        f"{user_snippet}\n\nQuery: {state.user_query}"
    )
    criteria = await model.ainvoke(prompt)
    return {"extracted_criteria": criteria}


def build_query_text(state: QAGraphState) -> str:
    parts = [state.user_query]
    c = state.extracted_criteria
    if c:
        if getattr(c, "skills", None): parts.append(" ".join(c.skills))
        if getattr(c, "job_function", None): parts.append(c.job_function)
        if getattr(c, "seniority", None): parts.append(" ".join(c.seniority))
        if getattr(c, "location", None): parts.append(c.location)
        if getattr(c, "remote_type", None): parts.append(c.remote_type)
    return " ".join(parts)


async def hybrid_search(state: QAGraphState) -> dict:
    query_text = build_query_text(state)
    limit = state.extracted_criteria.limit if state.extracted_criteria else None
    async with async_session() as db:
        results = await search_jobs(db=db, query_text=query_text, result_limit=limit or 20)
    return {"retrieved_jobs": results}


def route_to_scoring(state: QAGraphState):
    if not state.retrieved_jobs:
        return "generate_draft"
    return [Send("score_candidate", {"user_query": state.user_query, "job_to_score": job}) for job in state.retrieved_jobs]


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
    limit = state.extracted_criteria.limit if state.extracted_criteria and state.extracted_criteria.limit else DEFAULT_TOP_N
    jobs_by_id = {str(j.id): j for j in state.retrieved_jobs}
    ranked = sorted(state.job_scores, key=lambda s: s.fit_score, reverse=True)
    top = [jobs_by_id[s.job_id] for s in ranked[:limit] if s.job_id in jobs_by_id]
    return {"retrieved_jobs": top, "job_scores": Overwrite(value=[])}


async def generate_draft(state: QAGraphState):
    if not state.retrieved_jobs:
        return {"draft_response": GeneratedResponse(insufficient_data=True, summary="No matching jobs found.", claims=[])}
    ctx = "\n".join(f"job_id={j.id} | {j.title} at {j.company_name} | skills={j.required_skills} | remote={j.remote_type} | loc={j.locations}" for j in state.retrieved_jobs)
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
    if not state.draft_response: return []
    return [c.job_id for c in state.draft_response.claims if c.job_id not in valid]


async def heuristic_check(state: QAGraphState) -> Command:
    if state.draft_response and state.draft_response.insufficient_data:
        return Command(goto=END)
    bad = find_ungrounded_claims(state)
    if not bad:
        return Command(goto="llm_critic")
    attempts = state.heuristic_attempts + 1
    if attempts >= MAX_HEURISTIC_ATTEMPTS:
        fb = GeneratedResponse(insufficient_data=True, summary="Couldn't produce grounded answer.", claims=[])
        return Command(goto=END, update={"draft_response": fb, "heuristic_attempts": attempts})
    return Command(goto="generate_draft", update={"heuristic_attempts": attempts, "grounding_error": ", ".join(bad)})


async def llm_critic(state: QAGraphState) -> Command:
    if not state.draft_response or state.draft_response.insufficient_data:
        return Command(goto=END)
    ctx = "\n".join(f"{j.id} | {j.title} at {j.company_name} | {j.required_skills}" for j in state.retrieved_jobs)
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
        return Command(goto=END, update={"verification_attempts": 0, "critique_feedback": None})
    attempts = state.verification_attempts + 1
    if attempts >= MAX_VERIFICATION_ATTEMPTS:
        fb = GeneratedResponse(insufficient_data=True, summary="Failed verification after retries.", claims=[])
        return Command(goto=END, update={"draft_response": fb, "verification_attempts": attempts})
    fb = "; ".join(crit.issues) if crit.issues else "Semantic mismatch"
    if crit.suggested_fix: fb += f" | Fix: {crit.suggested_fix}"
    return Command(goto="generate_draft", update={"verification_attempts": attempts, "critique_feedback": fb})


# ---------- Phase 4 HIL submit with interrupt ----------

def detect_submit_intent(state: QAGraphState) -> bool:
    q = (state.user_query or "").lower()
    return any(k in q for k in ["submit", "apply", "send application"])


async def intent_router(state: QAGraphState) -> Command:
    if detect_submit_intent(state):
        return Command(goto="prepare_submission")
    return Command(goto="hybrid_search")


async def prepare_submission(state: QAGraphState, *, store: Any | None = None):
    import re
    import uuid

    from sqlalchemy import select

    from app.core.db.models.job import Job

    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", state.user_query, re.I)
    job_id_str = m.group(0) if m else (str(state.retrieved_jobs[0].id) if state.retrieved_jobs else None)
    if not job_id_str:
        return {"draft_response": GeneratedResponse(insufficient_data=True, summary="Specify job ID to submit, or search first then say 'submit'.", claims=[]), "submission_preview": None}

    preview = {"job_id": job_id_str}
    app_id = None
    try:
        async with async_session() as db:
            job = await db.get(Job, uuid.UUID(job_id_str))
            if job: preview.update({"title": job.title, "company": job.company_name})
            if state.user_id:
                from app.core.db.models.application import Application
                q = await db.execute(select(Application).where(Application.user_id == uuid.UUID(state.user_id), Application.job_id == uuid.UUID(job_id_str), Application.status == "draft").limit(1))
                draft = q.scalar_one_or_none()
                if draft:
                    app_id = str(draft.id)
                    preview["resume_present"] = bool(draft.resume_draft)
    except Exception:
        pass
    return {"pending_job_id": job_id_str, "application_id": app_id, "submission_preview": preview}


async def request_human_approval(state: QAGraphState) -> Command:
    from langgraph.types import interrupt
    if not state.submission_preview or not state.pending_job_id:
        return Command(goto=END, update={"draft_response": GeneratedResponse(insufficient_data=True, summary="Missing job or draft for submission.", claims=[])})
    payload = {"action": "submit_application", "job_id": state.pending_job_id, "application_id": state.application_id, "preview": state.submission_preview, "message": f"Approve submission for job {state.pending_job_id}?"}
    human = interrupt(payload)
    approved = bool(human.get("approved") if isinstance(human, dict) else human) if human else False
    if approved:
        return Command(goto="execute_submission", update={"human_approval": True})
    return Command(goto=END, update={"draft_response": GeneratedResponse(insufficient_data=False, summary="Submission cancelled. Draft kept.", claims=[]), "human_approval": False})


async def execute_submission(state: QAGraphState):
    if not state.human_approval:
        return {"submission_result": {"status": "cancelled"}, "draft_response": GeneratedResponse(insufficient_data=False, summary="Not approved.", claims=[])}
    try:
        import uuid

        from app.core.db.models.application import Application
        if not state.user_id: raise PermissionError("Missing user context")
        async with async_session() as db:
            app_obj = None
            if state.application_id:
                app_obj = await db.get(Application, uuid.UUID(state.application_id))
            if not app_obj and state.pending_job_id:
                app_obj = Application(user_id=uuid.UUID(state.user_id), job_id=uuid.UUID(state.pending_job_id), status="draft")
                db.add(app_obj); await db.flush()
            if not app_obj: raise ValueError("Application not found")
            if str(app_obj.user_id) != str(state.user_id): raise PermissionError("Cross-tenant blocked")
            app_obj.status = "submitted"
            await db.commit(); await db.refresh(app_obj)
            return {"submission_result": {"status": "submitted", "application_id": str(app_obj.id)}, "application_id": str(app_obj.id), "draft_response": GeneratedResponse(insufficient_data=False, summary=f"Application {app_obj.id} submitted for job {state.pending_job_id}.", claims=[])}
    except Exception as e:
        return {"submission_result": {"status": "failed", "error": str(e)}, "draft_response": GeneratedResponse(insufficient_data=True, summary=f"Submission failed: {e}", claims=[])}
