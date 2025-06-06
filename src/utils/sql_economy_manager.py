# src/utils/sql_economy_manager.py

from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import select
from src.database.db import get_session
from src.database.models import User


class SqlEconomyManager:
    """
    SQL‐backed economy manager. All methods are async and operate
    directly on the `User` table’s gold, dust, and last_daily_claim.
    """

    async def get_balance(self, user_id: str) -> int:
        """
        Return the current gold balance for this user (0 if not found).
        """
        async with get_session() as session:
            stmt = select(User).where(User.user_id == str(user_id))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            return user.gold if user else 0

    async def add_balance(self, user_id: str, amount: int) -> None:
        """
        Increment gold by `amount`. If the user doesn’t exist, do nothing.
        """
        async with get_session() as session:
            stmt = select(User).where(User.user_id == str(user_id))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                user.gold += amount
                session.add(user)
                await session.commit()

    async def deduct_balance(self, user_id: str, cost: int) -> bool:
        """
        Subtract `cost` from the user’s gold if they have enough.
        Return True if successful, False otherwise.
        """
        async with get_session() as session:
            stmt = select(User).where(User.user_id == str(user_id))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user and user.gold >= cost:
                user.gold -= cost
                session.add(user)
                await session.commit()
                return True
            return False

    async def get_dust(self, user_id: str) -> int:
        async with get_session() as session:
            stmt = select(User).where(User.user_id == str(user_id))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            return user.dust if user else 0

    async def add_dust(self, user_id: str, amount: int) -> None:
        async with get_session() as session:
            stmt = select(User).where(User.user_id == str(user_id))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                user.dust += amount
                session.add(user)
                await session.commit()

    async def can_claim_daily(self, user_id: str) -> bool:
        """
        Return True if 24h have passed since last_daily_claim (or if never claimed).
        """
        async with get_session() as session:
            stmt = select(User).where(User.user_id == str(user_id))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                return False
            if not user.last_daily_claim:
                return True
            return datetime.utcnow() - user.last_daily_claim >= timedelta(hours=24)

    async def claim_daily(self, user_id: str, amount: int) -> None:
        """
        Give `amount` gold and set last_daily_claim = now. If user doesn’t exist, do nothing.
        """
        async with get_session() as session:
            stmt = select(User).where(User.user_id == str(user_id))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                user.gold += amount
                user.last_daily_claim = datetime.utcnow()
                session.add(user)
                await session.commit()

    async def get_time_until_next_daily(self, user_id: str) -> Optional[timedelta]:
        """
        Return a timedelta until the next daily claim. If user doesn’t exist or can claim now, return None.
        """
        async with get_session() as session:
            stmt = select(User).where(User.user_id == str(user_id))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user or not user.last_daily_claim:
                return None

            elapsed = datetime.utcnow() - user.last_daily_claim
            if elapsed >= timedelta(hours=24):
                return None
            return timedelta(hours=24) - elapsed


