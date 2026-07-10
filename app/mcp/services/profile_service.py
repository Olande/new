from __future__ import annotations

from app.mcp.di import AuthenticatedUser
from app.mcp.exceptions import NotFoundError
from app.mcp.mcp_schemas import GetProfileOutput
from app.mcp.repositories.memory_repo import CareerMemoryRepository
from app.mcp.repositories.user_repo import UserRepository


class ProfileService:
    def __init__(self, user_repo: UserRepository, memory_repo: CareerMemoryRepository):
        self.user_repo = user_repo
        self.memory_repo = memory_repo

    async def get_profile(self, user: AuthenticatedUser) -> GetProfileOutput:
        """Retrieves user profile and aggregates career memories from Postgres Store, with legacy table fallback."""
        db_user = await self.user_repo.get_by_id(user.user_id)
        if not db_user:
            raise NotFoundError(f"User {user.user_id} not found")

        memories = []
        user_id_str = str(user.user_id)

        try:
            # Attempt to use PostgresStore if available in this process
            from app.core.config.settings import settings

            dsn = getattr(settings, "database_url", None)
            if dsn:
                from langgraph.store.postgres.aio import AsyncPostgresStore
                from psycopg_pool import AsyncConnectionPool

                pool = AsyncConnectionPool(
                    conninfo=dsn,
                    max_size=5,
                    kwargs={"autocommit": True, "prepare_threshold": 0},
                )
                await pool.open()
                store = AsyncPostgresStore(pool)
                await store.setup()
                # Search all entity types for this user
                for et in [
                    "skill",
                    "project",
                    "achievement",
                    "education",
                    "employment_history",
                ]:
                    try:
                        res = await store.asearch((user_id_str, et), limit=10)
                        for r in res:
                            memories.append(
                                {"type": et, "key": r.key, "content": r.value}
                            )
                    except Exception:
                        continue
                await pool.close()
        except Exception:
            pass

        if not memories:
            # Fallback to legacy career_memory table (your schema)
            db_memories = await self.memory_repo.get_memories_by_user_id(user.user_id)
            for m in db_memories[:20]:
                memories.append(
                    {
                        "type": m.entity_type.value
                        if hasattr(m.entity_type, "value")
                        else str(m.entity_type),
                        "key": m.fact_key,
                        "content": m.content,
                        "valid_from": m.valid_from.isoformat()
                        if m.valid_from
                        else None,
                    }
                )

        return GetProfileOutput(
            user_id=str(db_user.id),
            email=db_user.email,
            career_memories=memories,
        )
