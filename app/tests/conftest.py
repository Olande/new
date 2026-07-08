import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.db.models.embedding  # noqa: F401

# Import all models to register them in Base.metadata for tests
import app.core.db.models.user  # noqa: F401
import app.features.workflows.models  # noqa: F401
from app.core.db.base import Base
from app.features.applications.models import Application  # noqa
from app.features.jobs.models import Job, JobDescription, JobSource  # noqa
from app.features.matching.models import UserJobMatch  # noqa
from app.features.memory.models import CareerMemory  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    testingsessionlocal = async_sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )

    async with testingsessionlocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
