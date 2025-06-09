# src/database/db.py
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlmodel import SQLModel
from contextlib import asynccontextmanager

from src.utils.logger import get_logger
# EspritData and ConfigManager imports removed as they are no longer used here

log = get_logger(__name__)

DATABASE_URL = "sqlite+aiosqlite:///./nyxa.db"
engine = create_async_engine(DATABASE_URL, echo=True)

async def create_db_and_tables():
    log.info("Attempting to create database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    log.info("Database tables created or already exist.")

# The populate_static_data function has been removed.

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

@asynccontextmanager
async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

