import asyncio
import sys
import uuid
from datetime import datetime, timezone, timedelta
from loguru import logger
from sqlalchemy import select, update

from app.db.base import async_session
from app.db.models.agent_task import AgentTask
from app.graphs.master_graph import get_master_graph
from langgraph.errors import GraphInterrupt
from langgraph.types import Command


class AgentWorker:
    def __init__(self, name: str = "default-worker"):
        self.name = name
        self.running = False

    async def start(self):
        logger.info(f"Starting agent worker: {self.name}")
        self.running = True

        # Periodic stale task cleanup (run once on start, and every 5 mins)
        asyncio.create_task(self.reap_stale_tasks_loop())

        while self.running:
            try:
                task_processed = await self.poll_and_execute()
                if not task_processed:
                    await asyncio.sleep(1.0)
            except Exception as e:
                logger.exception(f"Error in worker main loop: {e}")
                await asyncio.sleep(2.0)

    async def stop(self):
        logger.info(f"Stopping agent worker: {self.name}")
        self.running = False

    async def poll_and_execute(self) -> bool:
        """Poll the DB for a pending task and execute it."""
        async with async_session() as session:
            # Query a pending task using SELECT FOR UPDATE SKIP LOCKED
            stmt = (
                select(AgentTask)
                .where(AgentTask.status == "pending")
                .order_by(AgentTask.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            res = await session.execute(stmt)
            task = res.scalar_one_or_none()

            if not task:
                return False

            logger.info(f"Claimed task: {task.id} (Graph: {task.graph_name})")
            task.status = "running"
            task.locked_at = datetime.now(timezone.utc)
            task.locked_by = self.name
            task.attempts += 1
            await session.commit()

            task_id = task.id
            payload = task.payload
            thread_id = task.thread_id
            graph_name = task.graph_name

        # Execute task outside the transaction session to keep connection pool free
        try:
            if graph_name != "main_graph":
                raise ValueError(f"Unsupported graph: {graph_name}")

            master_graph = await get_master_graph()
            config = {
                "configurable": {"thread_id": thread_id},
                "metadata": {
                    "thread_id": thread_id,
                    "stage": "initial",
                },
                "tags": [f"worker:{self.name}", f"task:{task_id}"],
            }

            # Extract initial state from payload
            initial_state = payload.get("initial_state") or payload
            resume_data = payload.get("resume_data")

            logger.info(f"Running master graph for thread: {thread_id}")

            try:
                # Run the graph
                if resume_data is not None:
                    # Update config metadata based on state
                    state_before = await master_graph.aget_state(config)
                    if state_before and state_before.values:
                        config["metadata"]["stage"] = state_before.values.get(
                            "stage", "unknown"
                        )
                        active_app = state_before.values.get("active_application_id")
                        if active_app:
                            # Try to add revision_count if we can fetch it (skipping full async DB read for simplicity here,
                            # but stage at least is updated).
                            pass

                    await master_graph.ainvoke(Command(resume=resume_data), config)

                    async with async_session.begin() as update_session:
                        task_record = await update_session.get(AgentTask, task_id)
                        if task_record and "resume_data" in task_record.payload:
                            new_payload = task_record.payload.copy()
                            del new_payload["resume_data"]
                            task_record.payload = new_payload
                else:
                    await master_graph.ainvoke(initial_state, config)

                # Check final status
                state = await master_graph.aget_state(config)
                if state.next:
                    # Thread paused at interrupt
                    await self.update_task_status(
                        task_id,
                        status="paused",
                        result={"next_nodes": list(state.next)},
                    )
                else:
                    # Graph completed
                    await self.update_task_status(
                        task_id, status="completed", result=state.values
                    )
            except GraphInterrupt:
                # Graph hit an interrupt (paused for human interaction)
                state = await master_graph.aget_state(config)
                await self.update_task_status(
                    task_id, status="paused", result={"next_nodes": list(state.next)}
                )

        except Exception as e:
            logger.exception(f"Task {task_id} failed with error: {e}")
            await self.update_task_status(task_id, status="failed", error=str(e))

        return True

    async def update_task_status(
        self,
        task_id: uuid.UUID,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ):
        """Update the final task state in the DB."""
        async with async_session.begin() as session:
            task = await session.get(AgentTask, task_id)
            if task:
                task.status = status
                task.updated_at = datetime.now(timezone.utc)
                if status in ("completed", "failed", "paused"):
                    task.completed_at = datetime.now(timezone.utc)
                if result is not None:
                    # Clean up result values for serialization (e.g. UUID to str)
                    task.result = self.serialize_clean(result)
                if error is not None:
                    task.error = error
                task.locked_by = None
                task.locked_at = None

    def serialize_clean(self, obj):
        """Recursively convert unserializable types to string."""
        if isinstance(obj, dict):
            return {k: self.serialize_clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.serialize_clean(x) for x in obj]
        elif isinstance(obj, (uuid.UUID, datetime)):
            return str(obj)
        elif hasattr(obj, "content"):  # LangChain messages
            return {"type": obj.__class__.__name__, "content": str(obj.content)}
        return obj

    async def reap_stale_tasks_loop(self):
        """Background task to reclaim tasks stuck in running status."""
        while self.running:
            try:
                await self.reap_stale_tasks()
            except Exception as e:
                logger.error(f"Error in stale task reaper: {e}")
            await asyncio.sleep(300.0)

    async def reap_stale_tasks(self):
        """Find running tasks with no update in the last 10 minutes and make them pending again."""
        ten_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
        async with async_session.begin() as session:
            stmt = (
                update(AgentTask)
                .where(
                    AgentTask.status == "running", AgentTask.locked_at < ten_mins_ago
                )
                .values(status="pending", locked_by=None, locked_at=None)
                .returning(AgentTask.id)
            )
            res = await session.execute(stmt)
            stale_ids = res.scalars().all()
            for tid in stale_ids:
                logger.warning(f"Reclaiming stale task: {tid}")


def main():
    worker_name = f"worker-{uuid.uuid4().hex[:6]}"
    if len(sys.argv) > 2 and sys.argv[1] == "--name":
        worker_name = sys.argv[2]

    worker = AgentWorker(worker_name)
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
    except Exception as e:
        logger.critical(f"Unhandled worker error: {e}")


if __name__ == "__main__":
    main()
