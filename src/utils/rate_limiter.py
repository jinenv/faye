# src/utils/rate_limiter.py
from typing import Dict, List
from datetime import datetime, timedelta
import asyncio

class RateLimiter:
    """
    Rate limiting to prevent spam and abuse
    Essential for scaling to thousands of users
    """
    def __init__(self, calls: int = 5, period: int = 60):
        self.calls = calls  # Number of allowed calls
        self.period = period  # Time period in seconds
        self.users: Dict[str, List[datetime]] = {}
        self.lock = asyncio.Lock()
    
    async def check(self, user_id: str) -> bool:
        """Check if user can make a call"""
        async with self.lock:
            now = datetime.now()
            
            if user_id not in self.users:
                self.users[user_id] = [now]
                return True
            
            # Remove old calls outside the period
            cutoff = now - timedelta(seconds=self.period)
            self.users[user_id] = [t for t in self.users[user_id] if t > cutoff]
            
            # Check if under limit
            if len(self.users[user_id]) < self.calls:
                self.users[user_id].append(now)
                return True
            
            return False
    
    async def get_cooldown(self, user_id: str) -> int:
        """Get seconds until user can make next call"""
        async with self.lock:
            if user_id not in self.users or not self.users[user_id]:
                return 0
            
            oldest_call = min(self.users[user_id])
            cooldown_end = oldest_call + timedelta(seconds=self.period)
            remaining = (cooldown_end - datetime.now()).total_seconds()
            
            return max(0, int(remaining))
    
    async def reset(self, user_id: str) -> None:
        """Reset rate limit for a user"""
        async with self.lock:
            if user_id in self.users:
                del self.users[user_id]
    
    async def cleanup(self) -> int:
        """Remove expired entries to prevent memory leak"""
        async with self.lock:
            cutoff = datetime.now() - timedelta(seconds=self.period)
            cleaned = 0
            
            for user_id in list(self.users.keys()):
                self.users[user_id] = [t for t in self.users[user_id] if t > cutoff]
                if not self.users[user_id]:
                    del self.users[user_id]
                    cleaned += 1
            
            return cleaned