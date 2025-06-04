# src/bot.py
import discord
from discord.ext import commands
from discord import app_commands # It's good practice to import app_commands if you're interacting with the tree directly
import os
import asyncio

# Import the logger
from src.utils.logger import get_logger # Assuming this path is correct based on your structure
log = get_logger(__name__)

# Import database functions
from src.database.db import create_db_and_tables, populate_static_data # Assuming this path is correct

# Import error handler
from src.utils.error_handler import handle_command_error # Assuming this path is correct

# Cog imports (primarily for type hinting or direct instantiation if needed, though load_extension uses strings)
# from src.cogs.start import Start # Not strictly necessary if only using load_extension
# from src.cogs.admin import Admin # Not strictly necessary if only using load_extension
# from src.cogs.summon_cog import SummonCog # Not strictly necessary if only using load_extension

class NyxaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True # Required for message content based commands if you use them
        super().__init__(command_prefix=commands.when_mentioned_or("!", "."), intents=intents)
        self.synced_guilds = set()  # To keep track of synced guilds if needed for more complex logic
        self._commands_synced = False # Flag to ensure sync happens only once on ready

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
            # Depending on severity, you might want to prevent the bot from starting
            # raise RuntimeError("Database initialization failed, cannot start bot.") from e

        # 2. Load Cogs
        cogs_to_load = [
            "src.cogs.admin",
            "src.cogs.summon_cog"  # Added SummonCog here
        ]

        for cog_path in cogs_to_load:
            try:
                await self.load_extension(cog_path)
                log.info(f"Successfully loaded {cog_path.split('.')[-1]} cog.")
            except commands.ExtensionAlreadyLoaded:
                log.warning(f"{cog_path.split('.')[-1]} cog was already loaded.")
            except commands.ExtensionNotFound:
                log.error(f"Could not find {cog_path.split('.')[-1]} cog at {cog_path}.")
            except commands.NoEntryPointError:
                log.error(f"{cog_path.split('.')[-1]} cog does not have a setup function.")
            except Exception as e:
                log.error(f"Failed to load {cog_path.split('.')[-1]} cog: {e}", exc_info=True)


        # 3. Add any direct tree commands (like testsync)
        # This is fine for simple test commands, but generally, commands should reside in cogs.
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
        if not self._commands_synced: # Only sync if not already done
            log.info("Attempting GLOBAL slash command sync (may take 10-60 minutes to appear) during on_ready...")
            try:
                synced_commands = await self.tree.sync() # Always force global sync
                log.info(f"Global Sync returned {len(synced_commands)} commands. Names: {[cmd.name for cmd in synced_commands]}")
                self.synced_guilds.add("global") # Mark global as synced
                self._commands_synced = True # Mark as synced to prevent re-syncing on reconnect
            except discord.errors.Forbidden:
                log.error("Failed to sync global commands: Bot lacks 'application.commands' scope or is not in the main guild if it's a User Bot (not recommended).")
            except Exception as e:
                log.error(f"Failed to perform GLOBAL slash command sync during on_ready: {e}", exc_info=True)
        # --- END MODIFIED ---

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await handle_command_error(ctx, error)

nyxa_bot = NyxaBot()