# src/bot.py
import os
import asyncio
import discord
from discord.ext import commands
from src.database.db import create_db_and_tables
from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager

logger = get_logger(__name__)

class NyxaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="/unused", intents=intents)
        self.config_manager = ConfigManager()
    
    async def setup_hook(self):
        # prepare DB & configs
        await create_db_and_tables()
        logger.info("Database ready & static data seeded.")
        
        # load all cogs (slash-only now)
        for cog in [
            "src.cogs.onboarding_cog",
            "src.cogs.economy_cog",
            "src.cogs.summon_cog",
            "src.cogs.esprit_cog",
            "src.cogs.admin_cog",
            "src.cogs.help_cog",
        ]:
            try:
                await self.load_extension(cog)
                logger.info(f"✅ Loaded {cog}")
            except Exception as e:
                logger.error(f"❌ Failed to load {cog}: {e}", exc_info=True)
        
        # sync slash commands
        await self.tree.sync()
        logger.info("Slash commands synced.")
    
    async def on_ready(self):
        self.start_time = discord.utils.utcnow()  # Track when bot started
        logger.info(f"NyxaBot is online as {self.user} (ID: {self.user.id}).")

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("DISCORD_TOKEN not set.")
        return
    
    bot = NyxaBot()
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())


