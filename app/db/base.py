from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config.settings import settings

engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


# Load all models to ensure relations/backrefs are registered on metadata
from app.db import models  # noqa: F401,E402
from sqlalchemy.orm import configure_mappers  # noqa: E402

configure_mappers()
