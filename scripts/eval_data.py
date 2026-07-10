"""Eval datasets: golden jobs and query examples for retrieval evaluation."""

import hashlib
import uuid

GOLDEN_JOBS = [
    {
        "key": "backend_fastapi_senior_remote",
        "title": "Senior Backend Engineer",
        "company_name": "Golden Eval Co",
        "required_skills": ["Python", "PostgreSQL", "FastAPI"],
        "description": "Senior backend engineer, Python and PostgreSQL, FastAPI, remote friendly.",
    },
    {
        "key": "backend_django_mid_onsite",
        "title": "Backend Engineer, Django",
        "company_name": "Other Eval Co",
        "required_skills": ["Python", "Django", "MySQL"],
        "description": "Mid-level backend engineer using Django and MySQL, onsite in Austin.",
    },
    {
        "key": "backend_go_staff_remote",
        "title": "Staff Backend Engineer",
        "company_name": "Third Eval Co",
        "required_skills": ["Go", "Kubernetes", "gRPC"],
        "description": "Staff engineer building high-throughput services in Go with gRPC, remote.",
    },
    {
        "key": "data_sci_langchain",
        "title": "Data Scientist, Applied AI",
        "company_name": "Golden Eval Co",
        "required_skills": ["Python", "LangChain", "LLMs"],
        "description": "Applied AI team building LLM powered products with LangChain, New York.",
    },
    {
        "key": "data_sci_classical_ml",
        "title": "Data Scientist, Forecasting",
        "company_name": "Other Eval Co",
        "required_skills": ["Python", "scikit-learn", "Statistics"],
        "description": "Classical ML for demand forecasting, scikit-learn, statistics background, remote.",
    },
    {
        "key": "frontend_react_junior",
        "title": "Junior Frontend Developer",
        "company_name": "Golden Eval Co",
        "required_skills": ["React", "TypeScript"],
        "description": "Junior frontend role, React and TypeScript, customer facing products.",
    },
    {
        "key": "frontend_vue_senior",
        "title": "Senior Frontend Engineer, Vue",
        "company_name": "Other Eval Co",
        "required_skills": ["Vue", "TypeScript", "GraphQL"],
        "description": "Senior frontend engineer, Vue and GraphQL, design systems focus.",
    },
]

GOLDEN_JOB_IDS = {
    job["key"]: uuid.uuid5(uuid.NAMESPACE_DNS, job["key"]) for job in GOLDEN_JOBS
}

# Each query tagged with query_style so eval can be split, not blended:
#   "exact_terms"  -> reuses literal skill/tool names, should favor BM25
#   "paraphrase"   -> semantic rewording, should favor vector
#   "distractor"   -> deliberately similar to a DIFFERENT golden job in the
#                     same broad domain, testing real discrimination
#   "no_match"     -> genuinely no golden job fits, scored separately,
#                     not mixed into MRR/NDCG aggregate
EXAMPLES = [
    # --- Exact terms, should favor BM25 ---
    {
        "query": "FastAPI PostgreSQL backend engineer",
        "job": "backend_fastapi_senior_remote",
        "style": "exact_terms",
    },
    {
        "query": "Django MySQL backend engineer Austin",
        "job": "backend_django_mid_onsite",
        "style": "exact_terms",
    },
    {
        "query": "Go gRPC Kubernetes staff engineer",
        "job": "backend_go_staff_remote",
        "style": "exact_terms",
    },
    {
        "query": "LangChain LLM data scientist New York",
        "job": "data_sci_langchain",
        "style": "exact_terms",
    },
    {
        "query": "scikit-learn statistics forecasting data scientist",
        "job": "data_sci_classical_ml",
        "style": "exact_terms",
    },
    {
        "query": "React TypeScript junior frontend developer",
        "job": "frontend_react_junior",
        "style": "exact_terms",
    },
    {
        "query": "Vue GraphQL senior frontend engineer",
        "job": "frontend_vue_senior",
        "style": "exact_terms",
    },
    # --- Paraphrased, should favor vector ---
    {
        "query": "Experienced engineer building scalable Python web services and relational data models, open to remote",
        "job": "backend_fastapi_senior_remote",
        "style": "paraphrase",
    },
    {
        "query": "Backend developer maintaining a Django based e-commerce platform in person",
        "job": "backend_django_mid_onsite",
        "style": "paraphrase",
    },
    {
        "query": "Systems engineer designing high performance microservices in a compiled language",
        "job": "backend_go_staff_remote",
        "style": "paraphrase",
    },
    {
        "query": "AI practitioner building generative product features on top of large language models",
        "job": "data_sci_langchain",
        "style": "paraphrase",
    },
    {
        "query": "Quantitative analyst building predictive demand models with traditional machine learning",
        "job": "data_sci_classical_ml",
        "style": "paraphrase",
    },
    {
        "query": "Entry level UI developer building customer interfaces with a component based framework",
        "job": "frontend_react_junior",
        "style": "paraphrase",
    },
    {
        "query": "Experienced UI engineer maintaining a shared design system and API layer",
        "job": "frontend_vue_senior",
        "style": "paraphrase",
    },
    # --- Distractors: similar domain, must pick the RIGHT one among peers ---
    {
        "query": "backend engineer remote",
        "job": "backend_fastapi_senior_remote",
        "style": "distractor",
    },
    {
        "query": "senior backend role",
        "job": "backend_go_staff_remote",
        "style": "distractor",
    },
    {
        "query": "data scientist New York",
        "job": "data_sci_langchain",
        "style": "distractor",
    },
    # --- No true match, evaluate separately (recall@k should be ~0) ---
    {
        "query": "mobile engineer Android Kotlin Jetpack Compose",
        "job": None,
        "style": "no_match",
    },
    {
        "query": "DevOps engineer Terraform AWS infrastructure",
        "job": None,
        "style": "no_match",
    },
    {
        "query": "product manager roadmap stakeholder alignment",
        "job": None,
        "style": "no_match",
    },
]


def dedup_hash(job_id: uuid.UUID) -> str:
    return hashlib.sha256(str(job_id).encode()).hexdigest()
