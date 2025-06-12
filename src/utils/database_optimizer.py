# src/utils/database_optimizer.py
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)

class DatabaseOptimizer:
    """Database optimization utilities for scaling"""
    
    @staticmethod
    async def create_indexes(session: AsyncSession):
        """Create database indexes for better performance"""
        indexes = [
            # User lookups
            "CREATE INDEX IF NOT EXISTS idx_user_id ON users(id)",
            "CREATE INDEX IF NOT EXISTS idx_user_level ON users(level)",
            
            # Esprit lookups
            "CREATE INDEX IF NOT EXISTS idx_user_esprit_owner ON user_esprits(owner_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_esprit_id ON user_esprits(id)",
            "CREATE INDEX IF NOT EXISTS idx_user_esprit_data ON user_esprits(esprit_data_id)",
            
            # Composite indexes for common queries
            "CREATE INDEX IF NOT EXISTS idx_user_esprit_owner_data ON user_esprits(owner_id, esprit_data_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_team ON users(active_esprit_id, support1_esprit_id, support2_esprit_id)",
        ]
        
        for index in indexes:
            try:
                await session.execute(text(index))
                logger.info(f"Created index: {index.split('idx_')[1].split(' ')[0]}")
            except Exception as e:
                logger.warning(f"Index creation failed (may already exist): {e}")
        
        await session.commit()
    
    @staticmethod
    async def analyze_tables(session: AsyncSession):
        """Run ANALYZE on tables for query optimization"""
        tables = ["users", "user_esprits", "esprit_data"]
        
        for table in tables:
            try:
                await session.execute(text(f"ANALYZE {table}"))
                logger.info(f"Analyzed table: {table}")
            except Exception as e:
                logger.error(f"Failed to analyze {table}: {e}")