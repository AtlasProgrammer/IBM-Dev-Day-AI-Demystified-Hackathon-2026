from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.core.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir() -> None:
    if settings.database_url.startswith("sqlite"):
        marker = "///"
        if marker in settings.database_url:
            rel = settings.database_url.split(marker, 1)[1]
            p = Path(rel).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir()

engine: AsyncEngine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

