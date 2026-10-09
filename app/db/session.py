from collections.abc import AsyncIterator, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Base, Document

settings = get_settings()

engine = create_async_engine(settings.postgres_dsn)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def replace_documents(documents: Sequence[Document]) -> None:
    async with session_factory.begin() as session:
        await session.execute(text("TRUNCATE TABLE documents RESTART IDENTITY"))
        session.add_all(documents)


async def close_db() -> None:
    await engine.dispose()
