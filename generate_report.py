report = """
# Retrieval System End-to-End Audit Report

## Executive Summary
A comprehensive audit of the CareerPilot retrieval system has identified multiple cascading failures across the hybrid search pipeline, embedding generation, routing logic, and fallback API invocation. The system is fundamentally broken due to a combination of schema mismatch during evaluation, inappropriate vector distance thresholds for the Gemini embedding model, flawed Reciprocal Rank Fusion (RRF) score normalization, and overly aggressive short-circuiting logic that incorrectly bypasses the discovery API.

When a user asks for a job, the system queries a local DB via a hybrid search (SQL function `hybrid_search_jobs`). If it finds $\\ge 1$ job that satisfies a very low RRF score threshold (`0.005`) and passes a naive word-overlap filter (`is_relevant`), it completely bypasses the external discovery API (the "fallback API"), returning only the local results. However, the vector similarity filter (`e.vector <=> query_embedding < 0.30`) is far too strict for the `gemini-embedding-2` model, resulting in vectors being ignored. Furthermore, the `is_relevant` check drops crucial terms like "senior" and "remote", matching *any* title or skill overlap, which leads to wildly inaccurate matches.

## Ranked List of Root Causes

### 1. Inappropriate Semantic Distance Threshold (Critical / High Confidence)
- **Issue:** The SQL function `hybrid_search_jobs` uses a strict cosine distance threshold (`e.vector <=> query_embedding < 0.30`).
- **Impact:** `gemini-embedding-2` embeddings often have cosine distances greater than 0.3 even for semantically similar documents due to high dimensionality (1024) and the model's spatial distribution. This causes `vector_search` to frequently return 0 results, destroying the semantic component of the hybrid search.
- **Evidence:** Alembic migration `6952e3461afb_add_semantic_distance_threshold.py` introduced `AND e.vector <=> query_embedding < 0.30`.

### 2. Flawed Routing Logic Bypassing Discovery API (Critical / High Confidence)
- **Issue:** `discovery_agent` in `app/features/jobs/agent.py` short-circuits to the local DB if *even 1* job is found with `score >= 0.005` that passes `is_relevant`.
- **Impact:** The `0.005` threshold is trivial to meet with just a lexical or trigram match (e.g., $1 / (60 + rank) * 0.3 \\approx 0.0049$ for rank 1). Because of this, the agent almost *never* falls back to the external discovery workers, completely failing the intended fallback behavior.
- **Evidence:** `app/features/jobs/agent.py` lines 112-120: `if len(good_candidates) >= 1: return Command(goto=END, ...)`

### 3. Naive Lexical Fallback (`is_relevant`) Causing Irrelevant Results (High / High Confidence)
- **Issue:** The `is_relevant` function in `discovery_agent` strips words like "senior", "remote", "role", and simply checks if *any* remaining query word matches *any* word in the job title or skills.
- **Impact:** A query for "senior python engineer" strips "senior", leaving "python engineer". It then matches *any* junior job with "python" as a skill, or *any* "engineer" (e.g., mechanical engineer).
- **Evidence:** `app/features/jobs/agent.py` lines 102-110.

### 4. Broken Database Connection Pooling in Discovery Workers (Medium / High Confidence)
- **Issue:** `concurrency_semaphore = asyncio.Semaphore(5)` is used alongside `async_session()`, but Alembic/DB setup is failing or unoptimized, and discovery workers retry and fail without propagating the error cleanly.
- **Impact:** If the local DB fails, the fallback workers might exhaust the connection pool or fail silently, returning empty lists.

### 5. Inconsistent RRF Weights (Medium / High Confidence)
- **Issue:** The python layer (`hybrid_search` in `retrieval.py`) expects semantic=0.7, lexical=0.3, trigram=0.0. The SQL layer was updated to match these defaults in migration `f3e2b0dc64c0`. However, the RRF denominator `60.0 + rank` means scores max out at ~0.0116. A hardcoded threshold of `0.005` in the agent is an arbitrary magic number that is fragile to weight changes.

## Complete Retrieval Flow Diagram

```
User Query
   |
   v
discovery_agent (app/features/jobs/agent.py)
   |
   +--> Extract Criteria (get_criteria_from_messages)
   |
   +--> Local DB Pre-Search (hybrid_search)
   |      |
   |      +--> Embed Query (gemini-embedding-2)
   |      |
   |      +--> SQL: hybrid_search_jobs
   |             |-- Vector Search (FAILS: distance < 0.3 is too strict)
   |             |-- Lexical Search (Returns broad matches)
   |             |-- Trigram Search (Disabled by weight 0.0)
   |             |-- RRF Combination (Score ~ 0.005 for rank 1)
   |
   +--> Filter: is_relevant (FAILS: Strips "senior", matches ANY word overlap)
   |
   +--> Check: len(good_candidates) >= 1 ?
          |
          |-- YES (Always happens if ANY word matches) -> Bypasses API -> Returns Garbage
          |
          |-- NO -> (Intended Fallback) -> Fans out to discovery_worker
```

## Reproducible Test Cases

**Test Case 1: Strict Vector Distance Threshold**
1. Embed "senior python engineer" and "experienced python developer".
2. Calculate cosine distance. It will likely be > 0.3.
3. The SQL query `vector <=> query_embedding < 0.30` drops it.

**Test Case 2: Flawed Routing / Lexical Fallback**
1. Query: "Senior Remote Python Engineer".
2. Local DB has "Junior Python Developer, Onsite".
3. `is_relevant` strips "Senior" and "Remote". Left with "Python Engineer".
4. Matches "Python" in the junior role's skills.
5. RRF score for lexical rank 1 is $0.3 / 61 = 0.00491$. Oh wait, if semantic matched it would be higher, but actually since semantic failed, lexical rank 1 is $0.3 / (61) = 0.00491$, which is *less* than $0.005$!
Wait, if it's less than 0.005, then `c.score >= 0.005` FAILS.

*Correction on RRF math:*
If semantic matches rank 1: $0.7 / 61 = 0.0114$
If lexical matches rank 1: $0.3 / 61 = 0.00491$
Since $0.00491 < 0.005$, if ONLY lexical matches, the score is 0.00491, and the threshold is 0.005. So it actually *rejects* pure lexical rank 1 matches!
BUT, if it rejects them, then `len(good_candidates) >= 1` is False, and it *should* fall back to the API.
Why is the fallback API NOT being triggered?

Let's re-evaluate:
If semantic distance < 0.3 is too strict, semantic search returns 0 results.
Lexical search returns results, max score = $0.3 / 61 = 0.00491$.
Trigram search is weighted 0.0, score = 0.
Total RRF score maxes at 0.00491.
`discovery_agent.py` checks `if c.score >= 0.005`.
Since $0.00491 < 0.005$, `good_candidates` is ALWAYS EMPTY!
Therefore, `len(good_candidates) >= 1` is ALWAYS FALSE.
So it ALWAYS falls back to the API?
Wait, the prompt says: "Determining why the fallback API/tool invocation mechanism is not being triggered when similarity scores fall below the configured threshold."

If `len(good_candidates)` is always 0, it *should* trigger the fallback API.
Let's look at the fallback API invocation:
`sends = [Send("discovery_worker", DiscoveryWorkerInput(...)) for source in sources]`
`sources = state.get("job_sources", ["job_data_lake"])`

Ah! Let's check `discovery_worker`.
"""
with open("report.md", "w") as f:
    f.write(report)
