import numpy as np
from sklearn.metrics import ndcg_score
from langsmith.schemas import Example, Run
from app.agents.critic_agent import ResumeEvaluator
from app.core.llm import get_llm
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger


def ndcg_at_10(run: Run, example: Example) -> dict:
    """Evaluate retrieval results using NDCG@10 via scikit-learn."""
    try:
        ranked_job_ids = run.outputs.get("ranked_job_ids", [])
        expected_job_id = example.outputs.get("expected_job_id")

        if not ranked_job_ids:
            return {"key": "ndcg_at_10", "score": 0.0}

        # If the expected job is completely absent, NDCG is 0
        if expected_job_id not in ranked_job_ids[:10]:
            return {"key": "ndcg_at_10", "score": 0.0}

        # Binary relevance: 1 if expected job is in ranked list, 0 otherwise
        k = max(10, len(ranked_job_ids))
        y_true = np.zeros((1, k))
        y_score = np.zeros((1, k))

        for i, j_id in enumerate(ranked_job_ids[:10]):
            y_score[0, i] = 10 - i  # Higher score for earlier ranks
            if j_id == expected_job_id:
                y_true[0, i] = 1

        score = ndcg_score(y_true, y_score, k=10)
        return {"key": "ndcg_at_10", "score": float(score)}
    except Exception as e:
        logger.error(f"Error computing NDCG@10: {e}")
        return {"key": "ndcg_at_10", "score": 0.0}


def mrr(run: Run, example: Example) -> dict:
    """Compute Mean Reciprocal Rank."""
    ranked_job_ids = run.outputs.get("ranked_job_ids", [])
    expected_job_id = example.outputs.get("expected_job_id")

    for i, j_id in enumerate(ranked_job_ids):
        if j_id == expected_job_id:
            return {"key": "mrr", "score": 1.0 / (i + 1)}

    return {"key": "mrr", "score": 0.0}


async def rubric_evaluator(run: Run, example: Example) -> dict:
    """Uses LLM-as-judge (with structured output) to evaluate the resume draft."""
    try:
        draft = run.outputs.get("resume_draft", "")
        inputs = example.inputs

        prompt = ChatPromptTemplate.from_template(
            "Evaluate this draft resume against the target job '{job_title}' at '{company_name}'.\n\n"
            "Resume Draft:\n{resume_draft}\n\n"
            "User Career Memory:\n{career_memory}\n\n"
            "Provide a short critique and a fitness score between 0.0 and 1.0."
        )

        structured_llm = get_llm().with_structured_output(ResumeEvaluator)
        chain = prompt | structured_llm

        res = await chain.ainvoke(
            {
                "resume_draft": draft,
                "job_title": inputs.get("job_title", ""),
                "company_name": inputs.get("company_name", ""),
                "career_memory": str(inputs.get("career_memory", [])),
            }
        )

        return {
            "key": "rubric_score",
            "score": res.resume_score,
            "comment": res.resume_critique,
        }
    except Exception as e:
        logger.error(f"Error in rubric_evaluator: {e}")
        return {"key": "rubric_score", "score": 0.0, "comment": str(e)}


async def hallucination_evaluator(run: Run, example: Example) -> dict:
    """Checks if the resume hallucinates skills not in the career memory."""
    try:
        draft = run.outputs.get("resume_draft", "")
        inputs = example.inputs

        prompt = ChatPromptTemplate.from_template(
            "Does this resume draft hallucinate any skills or experiences NOT present in the user's career memory?\n\n"
            "Resume Draft:\n{resume_draft}\n\n"
            "User Career Memory:\n{career_memory}\n\n"
            "Answer purely 'YES' if it hallucinates, or 'NO' if all claims are supported by the career memory."
        )

        llm = get_llm()
        chain = prompt | llm

        res = await chain.ainvoke(
            {
                "resume_draft": draft,
                "career_memory": str(inputs.get("career_memory", [])),
            }
        )

        content = res.content.strip().upper()
        # Score 1.0 if NO hallucination, 0.0 if YES
        score = 1.0 if "NO" in content else 0.0

        return {"key": "no_hallucination", "score": score, "comment": res.content}
    except Exception as e:
        logger.error(f"Error in hallucination_evaluator: {e}")
        return {"key": "no_hallucination", "score": 0.0, "comment": str(e)}
