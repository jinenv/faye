import os
from typing import AsyncGenerator
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from src.utils.logger import Logger
from contextlib import asynccontextmanager # <--- ADDED THIS IMPORT

log = Logger(__name__)

SQLITE_FILE_NAME = "nyxa.db"
# BASE_DIR: Get the absolute path to the project root
# It goes up three levels from src/database/db.py to C:/Project X
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(BASE_DIR, SQLITE_FILE_NAME)}"

# Create the asynchronous engine
# connect_args={"check_same_thread": False} is needed for SQLite with AsyncSession
# because SQLite does not allow threads to write to the same connection.
# For production, consider using a different database like PostgreSQL or MySQL.
engine = create_async_engine(DATABASE_URL, echo=True, connect_args={"check_same_thread": False})

async def create_db_and_tables():
    """
    Asynchronously creates all database tables defined in SQLModel models.
    """
    log.info("Attempting to create database tables...")
    async with engine.connect() as connection: # Use async with engine.connect() for DDL
        await connection.run_sync(SQLModel.metadata.create_all) # Run the sync DDL operation on the connection
    log.info("Database tables created (or already exist).")

@asynccontextmanager # <--- ADDED THIS DECORATOR
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Asynchronously provides an asynchronous database session.
    Use with 'async with get_session() as session:'.
    """
    log.debug("Getting new database session...")
    async with AsyncSession(engine) as session:
        try:
            yield session
        finally:
            await session.close()
            log.debug("Database session closed.")