import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config.settings import settings


async def main():
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Create a dummy vector of 1024 zeros for testing
        dummy_vector = "[" + ",".join(["0.0"] * 1024) + "]"
        query = text("""
            SELECT * FROM hybrid_search_jobs(
                :query_embedding,
                :query_text,
                :k
            );
        """)
        try:
            result = await session.execute(
                query,
                {
                    "query_embedding": dummy_vector,
                    "query_text": "software engineer",
                    "k": 10,
                },
            )
            print("Query executed successfully")
            print(result.all())
        except Exception as e:
            print("Error:", e)

    await engine.dispose()


asyncio.run(main())
