import uuid

from langsmith import Client
from loguru import logger

from app.core.config.settings import settings

GOLDEN_JOB_IDS = {
    "backend": uuid.UUID("11111111-1111-1111-1111-111111111111"),
    "data_sci": uuid.UUID("22222222-2222-2222-2222-222222222222"),
    "frontend": uuid.UUID("33333333-3333-3333-3333-333333333333"),
}


def seed_golden_jobs() -> dict:
    import asyncio
    import hashlib

    from app.db.base import async_session
    from app.db.models.job import Job
    from app.db.models.job_description import JobDescription

    def _dedup_hash(job_id: uuid.UUID) -> str:
        return hashlib.sha256(str(job_id).encode()).hexdigest()

    async def _seed():
        golden_jobs = [
            {
                "id": GOLDEN_JOB_IDS["backend"],
                "title": "Senior Backend Engineer",
                "company_name": "Golden Eval Co",
                "required_skills": ["Python", "PostgreSQL", "FastAPI"],
                "description": (  # FastMCP's sse_app is actually a bound method or property returning Starlette app.
                    "We are looking for a senior backend engineer with strong "
                    "Python and PostgreSQL experience to build scalable services. "
                    "Remote friendly."
                ),
            },
            {
                "id": GOLDEN_JOB_IDS["data_sci"],
                "title": "Data Scientist, Applied AI",
                "company_name": "Golden Eval Co",
                "required_skills": ["Python", "LangChain", "LLMs"],
                "description": (
                    "Join our applied AI team building LLM powered products "
                    "with LangChain. Based in New York."
                ),
            },
            {
                "id": GOLDEN_JOB_IDS["frontend"],
                "title": "Junior Frontend Developer",
                "company_name": "Golden Eval Co",
                "required_skills": ["React", "TypeScript"],
                "description": (
                    "Junior frontend role building React and TypeScript "
                    "interfaces for our customer facing products."
                ),
            },
        ]

        async with async_session() as session:
            for job_data in golden_jobs:
                existing = await session.get(Job, job_data["id"])
                if existing is not None:
                    continue

                job = Job(
                    id=job_data["id"],
                    dedup_hash=_dedup_hash(job_data["id"]),
                    title=job_data["title"],
                    company_name=job_data["company_name"],
                    required_skills=job_data["required_skills"],
                )
                session.add(job)

                description = JobDescription(
                    job_id=job_data["id"],
                    cleaned_text=job_data["description"],
                )
                session.add(description)

            await session.commit()

            from app.core.llm.embeddings import refresh_stale_embeddings

            logger.info("Generating embeddings for active/golden jobs...")
            await refresh_stale_embeddings(session)

        logger.info("Seeded golden jobs and generated embeddings.")

    asyncio.run(_seed())
    return GOLDEN_JOB_IDS


def seed_matching_dataset(client: Client) -> None:
    dataset_name = "careerpilot-matching-eval"

    job_ids = seed_golden_jobs()

    try:
        client.read_dataset(dataset_name=dataset_name)
        logger.info(f"Dataset '{dataset_name}' already exists.")
        return
    except Exception:
        logger.info(f"Creating dataset '{dataset_name}'...")

    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="Golden set of (user profile, job, relevance) triples for retrieval eval",
    )

    client.create_examples(
        inputs=[
            # Canonical matches
            {
                "query": "Senior Backend Engineer with Python and PostgreSQL experience, looking for remote work"
            },
            {"query": "Data Scientist focusing on LLMs and LangChain, in New York"},
            {"query": "Frontend Developer with React and TypeScript, junior level"},
            # Synonyms and paraphrases
            {
                "query": "Software engineer building backend APIs in Python with relational databases"
            },
            {
                "query": "Machine learning engineer creating generative AI applications using large language models"
            },
            {"query": "Entry level web developer experienced with TS and ReactJS"},
            # Noisy profiles
            {
                "query": (
                    "I previously worked in customer support, enjoy chess and photography, "
                    "but recently spent 6 years building FastAPI services with PostgreSQL."
                )
            },
            {
                "query": (
                    "Interested in startups, podcasts, AI newsletters and have strong "
                    "LangChain and prompt engineering experience."
                )
            },
            # Skill overlap challenges
            {
                "query": (
                    "Python developer focused on REST APIs, database design and backend systems"
                )
            },
            {
                "query": (
                    "Python developer focused on AI agents, retrieval systems and LLM evaluation"
                )
            },
            # Seniority reasoning
            {
                "query": (
                    "Recent graduate seeking first frontend role using React and TypeScript"
                )
            },
            {
                "query": (
                    "10 years of backend architecture experience leading Python platform teams"
                )
            },
            # Technology substitutions
            {
                "query": (
                    "Frontend engineer using JavaScript frameworks, component libraries and modern web tooling"
                )
            },
            {
                "query": (
                    "Applied AI engineer working with GPT applications and retrieval augmented generation"
                )
            },
            # Location mention
            {
                "query": (
                    "AI engineer located in Manhattan looking for in-person opportunities in New York"
                )
            },
            # Hard negatives
            {
                "query": (
                    "Mobile engineer developing Android applications with Kotlin and Jetpack Compose"
                )
            },
            {
                "query": (
                    "DevOps engineer focused on Kubernetes, Terraform and AWS infrastructure"
                )
            },
            {
                "query": (
                    "Product manager with experience leading roadmap planning and stakeholder alignment"
                )
            },
        ],
        outputs=[
            {"relevance": 1, "expected_job_id": str(job_ids["backend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["data_sci"])},
            {"relevance": 1, "expected_job_id": str(job_ids["frontend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["backend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["data_sci"])},
            {"relevance": 1, "expected_job_id": str(job_ids["frontend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["backend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["data_sci"])},
            {"relevance": 1, "expected_job_id": str(job_ids["backend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["data_sci"])},
            {"relevance": 1, "expected_job_id": str(job_ids["frontend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["backend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["frontend"])},
            {"relevance": 1, "expected_job_id": str(job_ids["data_sci"])},
            {"relevance": 1, "expected_job_id": str(job_ids["data_sci"])},
            {"relevance": 0, "expected_job_id": None},
            {"relevance": 0, "expected_job_id": None},
            {"relevance": 0, "expected_job_id": None},
        ],
        dataset_id=dataset.id,
    )

    logger.info(f"Seeded examples for '{dataset_name}'.")


def seed_generation_dataset(client: Client) -> None:
    dataset_name = "careerpilot-generation-eval"

    try:
        client.read_dataset(dataset_name=dataset_name)
        logger.info(f"Dataset '{dataset_name}' already exists.")
        return
    except Exception:
        logger.info(f"Creating dataset '{dataset_name}'...")

    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="Golden set of (career memory, job, expected resume sections) for resume generation eval",
    )

    client.create_examples(
        inputs=[
            # Baseline backend example
            {
                "career_memory": [
                    {
                        "fact_key": "experience_1",
                        "content": {"text": "5 years building Python microservices"},
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
            },
            # AI role
            {
                "career_memory": [
                    {
                        "fact_key": "experience_1",
                        "content": {
                            "text": "Built LLM-powered assistants and RAG pipelines"
                        },
                    },
                    {
                        "fact_key": "skill_1",
                        "content": {
                            "text": "LangChain, vector databases, prompt engineering"
                        },
                    },
                ],
                "job_title": "Applied AI Engineer",
                "company_name": "AI Labs",
                "required_skills": ["Python", "LangChain", "LLMs"],
                "job_description": "Build AI products using modern LLM frameworks.",
                "critique": None,
            },
            # Career transition
            {
                "career_memory": [
                    {
                        "fact_key": "experience_1",
                        "content": {
                            "text": "3 years in business analytics using Python"
                        },
                    },
                    {
                        "fact_key": "project_1",
                        "content": {
                            "text": "Built internal dashboards and predictive models"
                        },
                    },
                ],
                "job_title": "Junior Data Scientist",
                "company_name": "Insight Analytics",
                "required_skills": ["Python", "Statistics"],
                "job_description": "Entry level data science position.",
                "critique": None,
            },
            # Sparse memory
            {
                "career_memory": [
                    {
                        "fact_key": "skill_1",
                        "content": {"text": "React and TypeScript"},
                    }
                ],
                "job_title": "Frontend Developer",
                "company_name": "Web Studio",
                "required_skills": ["React", "TypeScript"],
                "job_description": "Build modern web applications.",
                "critique": None,
            },
            # Revision / critique test
            {
                "career_memory": [
                    {
                        "fact_key": "experience_1",
                        "content": {
                            "text": "Built backend APIs using FastAPI and PostgreSQL"
                        },
                    }
                ],
                "job_title": "Backend Engineer",
                "company_name": "Scale Systems",
                "required_skills": ["Python", "FastAPI"],
                "job_description": "Backend engineering role.",
                "critique": (
                    "Previous resume under-emphasized measurable impact and lacked achievements."
                ),
            },
        ],
        outputs=[
            {"expected_format": "resume_string"},
            {"expected_format": "resume_string"},
            {"expected_format": "resume_string"},
            {"expected_format": "resume_string"},
            {"expected_format": "resume_string"},
        ],
        dataset_id=dataset.id,
    )

    logger.info(f"Seeded examples for '{dataset_name}'.")


def seed_datasets() -> None:
    client = Client(api_key=settings.langsmith_api_key)
    seed_matching_dataset(client)
    seed_generation_dataset(client)


if __name__ == "__main__":
    seed_datasets()
