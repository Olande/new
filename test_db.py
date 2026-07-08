import asyncio

from sqlalchemy.orm import selectinload

from app.core.db.base import async_session
from app.features.jobs.models import Job


async def test():
    async with async_session() as session:
        try:
            job = await session.get(
                Job,
                "8289df7f-5179-4e8b-8154-b0461e180c79",
                options=[selectinload(Job.description)],
            )
            print(f"Success 1! Description: {job.description}")
        except Exception as e:
            print(f"Error 1: {e}")

    async with async_session() as session:
        try:
            job = await session.get(
                Job,
                "8289df7f-5179-4e8b-8154-b0461e180c79",
                options=[selectinload("description")],
            )
            print(f"Success 2! Description: {job.description}")
        except Exception as e:
            print(f"Error 2: {e}")


if __name__ == "__main__":
    from sqlalchemy.orm import configure_mappers

    configure_mappers()
    asyncio.run(test())
