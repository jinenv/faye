# src/database/db.py
"""
Central DB helpers:
• engine / session factory
• async get_session() context-manager
• create_db_and_tables() ─ plain async function
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = "sqlite+aiosqlite:///faye.db"

engine: AsyncEngine = create_async_engine(
    DATABASE_URL, echo=False, future=True
)

# factory used everywhere
SessionLocal = async_sessionmaker(
    engine, expire_on_commit=False
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession – used via `async with get_session():`."""
    async with SessionLocal() as session:
        yield session


async def create_db_and_tables() -> None:
    """Create all tables once at startup (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

