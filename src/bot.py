# src/bot.py
import os
import asyncio
import discord
from discord.ext import commands
from src.database.db import create_db_and_tables, populate_static_data
from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager

logger = get_logger(__name__)

class NyxaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        # A prefix is not needed for a slash-command-only bot,
        # but the argument is required. This will not be used.
        super().__init__(command_prefix=commands.when_mentioned_or("$"), intents=intents)
        self.config_manager = ConfigManager()

    async def setup_hook(self):
        await create_db_and_tables()
        await populate_static_data(self.config_manager)
        logger.info("Database tables created and static data seeded.")

        cogs_to_load = [
            "src.cogs.onboarding_cog",
            "src.cogs.economy_cog",
            "src.cogs.summon_cog",
            "src.cogs.esprit_cog",
            "src.cogs.admin_cog"
        ]
        for cog in cogs_to_load:
            await self.load_extension(cog)
        logger.info("All cogs loaded successfully.")

        await self.tree.sync()
        logger.info("Slash commands synced with Discord.")

    async def on_ready(self):
        logger.info(f"NyxaBot is online as {self.user} (ID: {self.user.id}).")

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("DISCORD_TOKEN is not set in the environment.")
        return
    
    bot = NyxaBot()
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
