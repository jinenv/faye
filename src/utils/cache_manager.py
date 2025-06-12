# src/utils/cache_manager.py
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
import json

class CacheManager:
    """
    Thread-safe caching system for the bot
    Reduces database load for frequently accessed data
    """
    def __init__(self, default_ttl: int = 300):
        self.cache: Dict[str, Any] = {}
        self.timestamps: Dict[str, datetime] = {}
        self.default_ttl = default_ttl
        self.lock = asyncio.Lock()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }
    
    async def get(self, key: str, ttl: Optional[int] = None) -> Optional[Any]:
        """Get value from cache with TTL check"""
        async with self.lock:
            if key in self.cache:
                # Check if expired
                ttl_seconds = ttl or self.default_ttl
                if datetime.now() - self.timestamps[key] > timedelta(seconds=ttl_seconds):
                    # Expired, remove it
                    del self.cache[key]
                    del self.timestamps[key]
                    self.stats["evictions"] += 1
                    self.stats["misses"] += 1
                    return None
                
                self.stats["hits"] += 1
                return self.cache[key]
            
            self.stats["misses"] += 1
            return None
    
    async def set(self, key: str, value: Any) -> None:
        """Set value in cache"""
        async with self.lock:
            self.cache[key] = value
            self.timestamps[key] = datetime.now()
    
    async def delete(self, key: str) -> bool:
        """Delete specific key from cache"""
        async with self.lock:
            if key in self.cache:
                del self.cache[key]
                del self.timestamps[key]
                return True
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern (e.g., 'user:123:*')"""
        async with self.lock:
            keys_to_delete = [k for k in self.cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self.cache[key]
                del self.timestamps[key]
            return len(keys_to_delete)
    
    async def get_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        async with self.lock:
            total = self.stats["hits"] + self.stats["misses"]
            hit_rate = self.stats["hits"] / total * 100 if total > 0 else 0
            return {
                **self.stats,
                "size": len(self.cache),
                "hit_rate": round(hit_rate, 2)
            }
    
    async def cleanup(self) -> int:
        """Remove all expired entries"""
        async with self.lock:
            now = datetime.now()
            expired_keys = []
            
            for key, timestamp in self.timestamps.items():
                if now - timestamp > timedelta(seconds=self.default_ttl):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
                del self.timestamps[key]
                self.stats["evictions"] += 1
            
            return len(expired_keys)