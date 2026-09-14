import os
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    database_url = os.environ.get("DATABASE_URL")
    assert database_url, "DATABASE_URL environment variable is not set"
    engine = create_async_engine(database_url)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with get_sessionmaker()() as session:
        yield session
