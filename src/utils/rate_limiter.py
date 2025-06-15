#src.utils.rate_limiter.py
#add import aioredis when needed for scale
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import asyncio

class RateLimiter:
    def __init__(self, calls: int = 5, period: int = 60, redis=None):
        self.calls = calls
        self.period = period
        self.redis = redis  # aioredis.Redis or None for in-memory fallback
        self.users: Dict[str, List[datetime]] = {}
        self.lock = asyncio.Lock()
    
    async def check(self, user_id: str) -> bool:
        if self.redis:
            key = f"ratelimit:{user_id}"
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.period)
            return count <= self.calls
        # fallback to memory
        async with self.lock:
            now = datetime.now()
            if user_id not in self.users:
                self.users[user_id] = [now]
                return True
            cutoff = now - timedelta(seconds=self.period)
            self.users[user_id] = [t for t in self.users[user_id] if t > cutoff]
            if len(self.users[user_id]) < self.calls:
                self.users[user_id].append(now)
                return True
            return False
    
    async def get_cooldown(self, user_id: str) -> int:
        if self.redis:
            key = f"ratelimit:{user_id}"
            ttl = await self.redis.ttl(key)
            return max(0, ttl if ttl is not None else 0)
        async with self.lock:
            if user_id not in self.users or not self.users[user_id]:
                return 0
            oldest_call = min(self.users[user_id])
            cooldown_end = oldest_call + timedelta(seconds=self.period)
            remaining = (cooldown_end - datetime.now()).total_seconds()
            return max(0, int(remaining))
    
    async def reset(self, user_id: str) -> None:
        if self.redis:
            key = f"ratelimit:{user_id}"
            await self.redis.delete(key)
            return
        async with self.lock:
            if user_id in self.users:
                del self.users[user_id]
    
    async def cleanup(self) -> int:
        if self.redis:
            return 0  # not needed
        async with self.lock:
            cutoff = datetime.now() - timedelta(seconds=self.period)
            cleaned = 0
            for user_id in list(self.users.keys()):
                self.users[user_id] = [t for t in self.users[user_id] if t > cutoff]
                if not self.users[user_id]:
                    del self.users[user_id]
                    cleaned += 1
            return cleaned
