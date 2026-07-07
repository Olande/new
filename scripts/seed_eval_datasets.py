import os
import sys
from loguru import logger

try:
    from langsmith import Client
except ImportError:
    logger.error("langsmith is not installed")
    sys.exit(1)


def seed_datasets():
    if not os.getenv("LANGSMITH_API_KEY"):
        logger.error("LANGSMITH_API_KEY not set. Cannot seed datasets.")
        sys.exit(1)

    client = Client()

    # 1. Matching/Retrieval Golden Dataset
    dataset_name = "careerpilot-matching-eval"
    try:
        # Check if exists
        dataset = client.read_dataset(dataset_name=dataset_name)
        logger.info(f"Dataset '{dataset_name}' already exists.")
    except Exception:
        logger.info(f"Creating dataset '{dataset_name}'...")
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description="Golden set of (user profile, job, relevance) triples for retrieval eval",
        )

        client.create_examples(
            inputs=[
                {
                    "query": "Senior Backend Engineer with Python and PostgreSQL experience, looking for remote work"
                },
                {"query": "Data Scientist focusing on LLMs and LangChain, in New York"},
                {"query": "Frontend Developer with React and TypeScript, junior level"},
            ],
            outputs=[
                {"relevance": 1, "expected_job_id": "job_1_backend"},
                {"relevance": 1, "expected_job_id": "job_2_data_sci"},
                {"relevance": 1, "expected_job_id": "job_3_frontend"},
            ],
            dataset_id=dataset.id,
        )
        logger.info(f"Seeded examples for '{dataset_name}'.")

    # 2. Generation/Resume Golden Dataset
    gen_dataset_name = "careerpilot-generation-eval"
    try:
        dataset_gen = client.read_dataset(dataset_name=gen_dataset_name)
        logger.info(f"Dataset '{gen_dataset_name}' already exists.")
    except Exception:
        logger.info(f"Creating dataset '{gen_dataset_name}'...")
        dataset_gen = client.create_dataset(
            dataset_name=gen_dataset_name,
            description="Golden set of (career memory, job, expected resume sections) for resume generation eval",
        )

        client.create_examples(
            inputs=[
                {
                    "career_memory": [
                        {
                            "fact_key": "experience_1",
                            "content": {
                                "text": "5 years building Python microservices"
                            },
                        },
                        {
                            "fact_key": "skill_1",
                            "content": {"text": "Expert in FastAPI and PostgreSQL"},
                        },
                    ],
                    "job_title": "Senior Python Backend Engineer",
                    "company_name": "Tech Corp",
                    "required_skills": ["Python", "FastAPI", "SQL"],
                    "job_description": "We are looking for a senior backend engineer to build scalable microservices.",
                    "critique": None,
                }
            ],
            outputs=[
                {
                    "expected_format": "resume_string"
                }  # We evaluate output based on rubric, not exact string match
            ],
            dataset_id=dataset_gen.id,
        )
        logger.info(f"Seeded examples for '{gen_dataset_name}'.")


if __name__ == "__main__":
    seed_datasets()
