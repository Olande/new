from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import all models to register them in Base.metadata and resolve names
from sqlalchemy.orm import (
    DeclarativeBase,
    configure_mappers,  # noqa: E402
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core.config.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
)

import app.core.db.models.embedding  # noqa: F401
import app.core.db.models.user  # noqa: F401
import app.features.applications.models  # noqa: F401
import app.features.jobs.models  # noqa: F401
import app.features.matching.models  # noqa: F401
import app.features.memory.models  # noqa: F401
import app.features.workflows.models  # noqa: F401
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


configure_mappers()
