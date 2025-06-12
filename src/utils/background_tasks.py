# src/utils/background_tasks.py
import asyncio
from asyncio.log import logger
from datetime import datetime
import discord
from discord.ext import tasks, commands

class BackgroundTasks(commands.Cog):
    """Background tasks for maintenance and optimization"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache_cleanup.start()
        self.rate_limit_cleanup.start()
    
    def cog_unload(self):
        self.cache_cleanup.cancel()
        self.rate_limit_cleanup.cancel()
    
    @tasks.loop(minutes=15)
    async def cache_cleanup(self):
        """Periodically clean up expired cache entries"""
        if hasattr(self.bot, 'cache_manager'):
            cleaned = await self.bot.cache_manager.cleanup()
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} expired cache entries")
    
    @tasks.loop(minutes=5)
    async def rate_limit_cleanup(self):
        """Clean up old rate limit entries"""
        for cog in self.bot.cogs.values():
            if hasattr(cog, 'esprit_group') and hasattr(cog.esprit_group, 'rate_limiter'):
                cleaned = await cog.esprit_group.rate_limiter.cleanup()
                if cleaned > 0:
                    logger.info(f"Cleaned {cleaned} rate limit entries from {cog.__class__.__name__}")
    
    @cache_cleanup.before_loop
    @rate_limit_cleanup.before_loop
    async def before_background_tasks(self):
        """Wait for bot to be ready before starting tasks"""
        await self.bot.wait_until_ready()