# src/utils/performance_monitor.py
import time
import psutil
import asyncio
from typing import Dict, List
from datetime import datetime
from collections import deque

class PerformanceMonitor:
    """Monitor bot performance for scaling optimization"""
    
    def __init__(self, window_size: int = 100):
        self.command_times: Dict[str, deque] = {}
        self.window_size = window_size
        self.start_time = datetime.now()
    
    async def track_command(self, command_name: str, execution_time: float):
        """Track command execution time"""
        if command_name not in self.command_times:
            self.command_times[command_name] = deque(maxlen=self.window_size)
        
        self.command_times[command_name].append(execution_time)
    
    async def get_stats(self) -> Dict:
        """Get performance statistics"""
        stats = {
            "uptime": str(datetime.now() - self.start_time),
            "memory_usage_mb": psutil.Process().memory_info().rss / 1024 / 1024,
            "cpu_percent": psutil.Process().cpu_percent(),
            "commands": {}
        }
        
        for cmd, times in self.command_times.items():
            if times:
                stats["commands"][cmd] = {
                    "avg_ms": sum(times) / len(times) * 1000,
                    "max_ms": max(times) * 1000,
                    "min_ms": min(times) * 1000,
                    "calls": len(times)
                }
        
        return stats