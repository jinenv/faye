# src/bot.py

import os
import asyncio
import logging

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
        super().__init__(command_prefix="!", intents=intents)

        # Create a single, shared instance of the ConfigManager
        self.config_manager = ConfigManager()

    async def setup_hook(self):
        # 1) Ensure database tables exist
        await create_db_and_tables()

        # 2) Seed static EspritData if needed (pass the shared config manager)
        await populate_static_data(self.config_manager)
        logger.info("Database tables created (if missing) and EspritData seeded.")

        # 3) Load cogs (order doesn’t strictly matter except you want /start first)
        await self.load_extension("src.cogs.onboarding_cog")   # /start
        await self.load_extension("src.cogs.economy_cog")      # /balance, /daily/inventory
        await self.load_extension("src.cogs.summon_cog")       # /summon
        await self.load_extension("src.cogs.admin_cog")        # /reset_db, etc.

        logger.info("All cogs loaded successfully.")

        # 4) Sync slash commands
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
