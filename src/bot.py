# src/bot.py
import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio

# Import the logger
from src.utils.logger import get_logger
log = get_logger(__name__)

# Import database functions
from src.database.db import create_db_and_tables, populate_static_data

# Import error handler
from src.utils.error_handler import handle_command_error

# Import the Start cog
from src.cogs.start import Start

# Import the Admin cog
from src.cogs.admin import Admin

class NyxaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned_or("!", "."), intents=intents)
        self.synced_guilds = set()
        self._commands_synced = False

    async def setup_hook(self):
        log.info("Running setup_hook...")

        # 1. Initialize Database
        try:
            await create_db_and_tables()
            log.info("Database initialized and tables created.")
            await populate_static_data()
            log.info("Static data population check completed.")
        except Exception as e:
            log.critical(f"Failed to initialize database: {e}", exc_info=True)

        # 2. Load Cogs
        try:
            await self.load_extension("src.cogs.start")
            log.info("Successfully loaded Start cog.")
        except Exception as e:
            log.error(f"Failed to load Start cog: {e}", exc_info=True)

        # Load Admin cog
        try:
            await self.load_extension("src.cogs.admin")
            log.info("Successfully loaded Admin cog.")
        except Exception as e:
            log.error(f"Failed to load Admin cog: {e}", exc_info=True)

        # 3. Add any direct tree commands (like testsync)
        @self.tree.command(name="testsync", description="A direct test command for troubleshooting slash command sync.")
        async def testsync_command(interaction: discord.Interaction):
            await interaction.response.send_message("Test sync successful!", ephemeral=True)
            log.info(f"User {interaction.user.id} used /testsync command.")
        log.info("DEBUG: Added direct '/testsync' command to bot.tree for diagnostic.")

        # Important: Command syncing is now handled exclusively in on_ready via GLOBAL sync.

    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = discord.utils.utcnow()

        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info("Bot is ready and online!")

        # --- MODIFIED: Always perform global sync, remove TEST_GUILD_ID check ---
        if not self._commands_synced:
            log.info("Attempting GLOBAL slash command sync (may take 10-60 minutes to appear) during on_ready...")
            try:
                synced_commands = await self.tree.sync() # Always force global sync
                log.info(f"Global Sync returned {len(synced_commands)} commands. Names: {[cmd.name for cmd in synced_commands]}")
                self.synced_guilds.add("global") # Mark global as synced

            except Exception as e:
                log.error(f"Failed to perform GLOBAL slash command sync during on_ready: {e}", exc_info=True)

            self._commands_synced = True # Mark as synced to prevent re-syncing on reconnect
        # --- END MODIFIED ---

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await handle_command_error(ctx, error)

nyxa_bot = NyxaBot()