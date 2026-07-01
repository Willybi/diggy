from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import os

DATABASE_URL = os.environ["DATABASE_URL"]

_engine_kwargs = {"echo": False}
if "postgresql" in DATABASE_URL:
    _engine_kwargs.update(pool_size=10, max_overflow=5, pool_pre_ping=True)

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
