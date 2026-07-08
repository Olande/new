import ir_measures
from ir_measures import RR, nDCG
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langsmith.schemas import Example, Run
from loguru import logger
from openevals.llm import create_async_llm_as_judge
from openevals.prompts import HALLUCINATION_PROMPT

from app.core.config.settings import settings

llm = init_chat_model(
    "gemini-3.1-flash-lite",
    model_provider="google_genai",
    api_key=settings.google_api_key,
)


retrieval_metrics_cache: dict[str, dict] = {}


def _extract_ranked_job_ids(run: Run) -> list[str]:
    ranked_jobs = run.outputs.get("ranked_jobs", [])
    if ranked_jobs and isinstance(ranked_jobs[0], dict):
        return [str(job["id"]) for job in ranked_jobs]

    return [str(job_id) for job_id in run.outputs.get("ranked_job_ids", [])]


def retrieval_metrics(run: Run, example: Example) -> dict:
    cache_key = run.id
    if cache_key in retrieval_metrics_cache:
        return retrieval_metrics_cache[cache_key]

    ranked_job_ids = _extract_ranked_job_ids(run)
    expected_job_id = str(example.outputs.get("expected_job_id"))

    qid = str(example.id)
    qrels = {qid: {expected_job_id: 1}}
    ir_run = {
        qid: {
            job_id: float(len(ranked_job_ids) - rank)
            for rank, job_id in enumerate(ranked_job_ids)
        }
    }

    result = ir_measures.calc_aggregate([nDCG @ 10, RR], qrels, ir_run)
    retrieval_metrics_cache[cache_key] = result
    return result


def ndcg_at_10(run: Run, example: Example) -> dict:
    try:
        if not run.outputs.get("ranked_job_ids") and not run.outputs.get("ranked_jobs"):
            return {"key": "ndcg_at_10", "score": 0.0}
        metrics = retrieval_metrics(run, example)
        return {"key": "ndcg_at_10", "score": float(metrics[nDCG @ 10])}
    except Exception as e:
        logger.error(f"Error computing NDCG@10: {e}")
        return {"key": "ndcg_at_10", "score": 0.0}


def mrr(run: Run, example: Example) -> dict:
    try:
        if not run.outputs.get("ranked_job_ids") and not run.outputs.get("ranked_jobs"):
            return {"key": "mrr", "score": 0.0}
        metrics = retrieval_metrics(run, example)
        return {"key": "mrr", "score": float(metrics[RR])}
    except Exception as e:
        logger.error(f"Error computing MRR: {e}")
        return {"key": "mrr", "score": 0.0}


RUBRIC_PROMPT = ChatPromptTemplate.from_template(
    "Evaluate this draft resume against the target job '{job_title}' at '{company_name}'.\n\n"
    "Resume Draft:\n{outputs}\n\n"
    "User Career Memory:\n{career_memory}\n\n"
    "Provide a short critique and a fitness score between 0.0 and 1.0."
)

rubric_judge = create_async_llm_as_judge(
    prompt=RUBRIC_PROMPT, judge=llm, feedback_key="rubric_score", continuous=True
)
hallucination_judge = create_async_llm_as_judge(
    prompt=HALLUCINATION_PROMPT, judge=llm, feedback_key="no_hallucination"
)


async def rubric_evaluator(run: Run, example: Example) -> dict:
    try:
        draft = run.outputs.get("resume_draft", "")
        inputs = example.inputs

        return await rubric_judge(
            inputs=inputs,
            outputs=draft,
            job_title=inputs.get("job_title", ""),
            company_name=inputs.get("company_name", ""),
            career_memory=str(inputs.get("career_memory", [])),
        )
    except Exception as e:
        logger.error(f"Error in rubric_evaluator: {e}")
        return {"key": "rubric_score", "score": 0.0, "comment": str(e)}


async def hallucination_evaluator(run: Run, example: Example) -> dict:
    try:
        draft = run.outputs.get("resume_draft", "")
        inputs = example.inputs
        result = await hallucination_judge(
            inputs=str(inputs),
            outputs=draft,
            context=str(inputs.get("career_memory", [])),
            reference_outputs=str(example.outputs),
        )
        result["score"] = not result["score"]
        return result
    except Exception as e:
        logger.error(f"Error in hallucination_evaluator: {e}")
        return {"key": "no_hallucination", "score": 0.0, "comment": str(e)}
