import asyncio
import logging
import uuid

from app.features.jobs.api import (
    discover_jobs,
    get_job,
    list_jobs,
    search_jobs,
)
from app.features.memory.api import (
    get_memory,
    store_memory,
)
from app.features.workflows.api import (
    get_task_status,
    run_workflow,
)

logging.basicConfig(level=logging.INFO)


async def test_mcp():
    print("--- 1. Testing list_jobs ---")
    res = await list_jobs(page_size=2)
    print(f"Total jobs: {res.total}, returned: {len(res.jobs)}")
    job_id = None
    if res.jobs:
        job_id = res.jobs[0].id

    print(f"--- 2. Testing get_job ({job_id}) ---")
    if job_id:
        res2 = await get_job(job_id=job_id)
        print(f"Get Job Result: {res2.title}")
    else:
        print("No job to get.")

    print("--- 3. Testing search_jobs ---")
    res3 = await search_jobs(query="python", k=2)
    print(f"Search jobs returned {len(res3.results)} results.")

    user_id = str(uuid.uuid4())
    print(f"--- 4. Testing store_memory (user: {user_id}) ---")
    res4 = await store_memory(
        user_id=user_id,
        entity_type="skill",
        fact_key="python",
        content="User loves python",
    )
    print(f"Store memory result: {res4.id}")

    print("--- 5. Testing get_memory ---")
    res5 = await get_memory(user_id=user_id)
    print(f"Get memory returned {len(res5.memories)} memories.")

    print("--- 6. Testing run_workflow ---")
    res6 = await run_workflow(user_id=user_id, query="Find me python jobs")
    print(f"Run workflow result: task_id={res6.task_id}")

    print("--- 7. Testing get_task_status ---")
    res7 = await get_task_status(task_id=res6.task_id)
    print(f"Get task status: {res7.status}")

    print("--- 8. Testing discover_jobs (dry run page_cap=1) ---")
    res8 = await discover_jobs(
        keywords=["python developer"], location="remote", page_cap=1
    )
    print(
        f"Discover jobs crawled {res8.pages_crawled} pages, created {res8.jobs_created}."
    )

    print("All MCP tests finished successfully!")


if __name__ == "__main__":
    asyncio.run(test_mcp())
