import asyncio

from sqlalchemy import select

from app.db.base import async_session
from app.db.models.job import Job


async def query():
    async with async_session() as session:
        result = await session.execute(select(Job))
        for job in result.scalars():
            print(f"ID: {job.id}, Title: {job.title}, Company: {job.company_name}")


asyncio.run(query())
