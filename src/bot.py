import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
from src.utils.logger import Logger
log = Logger(__name__)

class NyxaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)
        self.synced_guilds = set()
        self.initial_cogs = ["src.cogs.start"]

    async def setup_hook(self):
        log.info("Running setup_hook...")
        for cog in self.initial_cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Successfully loaded cog: {cog}")
            except Exception as e:
                log.error(f"Failed to load cog {cog}: {e}", exc_info=True)

        @self.tree.command(name="testsync", description="A direct test command for troubleshooting.")
        async def testsync_command(interaction: discord.Interaction):
            await interaction.response.send_message("Test sync successful!", ephemeral=True)
            log.info(f"User {interaction.user.id} used /testsync command.")
        log.info("DEBUG: Added direct 'testsync' command to bot.tree for diagnostic.")

        from src.database.db import create_db_and_tables
        try:
            await create_db_and_tables()
            log.info("Database initialized and tables created.")
        except Exception as e:
            log.error(f"Failed to initialize database: {e}", exc_info=True)


    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = discord.utils.utcnow()

        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info("Bot is ready and online!")

        # --- DEBUG: Log commands known to the tree *before* syncing ---
        known_commands = [cmd.name for cmd in self.tree.get_commands()]
        log.info(f"DEBUG: Commands in bot.tree BEFORE sync: {len(known_commands)} commands. Names: {known_commands}")
        # --- END DEBUG PRINT ---

        if self.user.id not in self.synced_guilds:
            try:
                # --- TEMPORARY GLOBAL SYNC TEST: COMMENT OUT THE TEST_GUILD_ID BLOCK ---
                # TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")
                # log.info(f"DEBUG: TEST_GUILD_ID from .env: '{TEST_GUILD_ID}'")
                # if TEST_GUILD_ID:
                #     guild = discord.Object(id=TEST_GUILD_ID)
                #     log.info(f"DEBUG: Attempting to clear commands for guild {TEST_GUILD_ID}...")
                #     try:
                #         self.tree.clear_commands(guild=guild)
                #         log.info(f"DEBUG: Successfully cleared commands for guild {TEST_GUILD_ID}.")
                #     except Exception as e:
                #         log.error(f"DEBUG: Failed to clear commands for guild {TEST_GUILD_ID}: {e}", exc_info=True)
                #     log.info(f"DEBUG: Attempting to sync commands for guild {TEST_GUILD_ID}...")
                #     synced_commands = await self.tree.sync(guild=guild)
                #     log.info(f"DEBUG: Sync command returned: {len(synced_commands)} commands. Names: {[cmd.name for cmd in synced_commands]}")
                #     log.info(f"Synced slash commands to test guild: {TEST_GUILD_ID}")
                # else:
                #     log.warning("TEST_GUILD_ID not found in .env. Slash commands not synced to a test guild.")

                # --- UNCOMMENT THESE LINES FOR GLOBAL SYNC TEST ---
                log.info("DEBUG: Attempting GLOBAL slash command sync...")
                synced_commands = await self.tree.sync() # Sync globally
                log.info(f"DEBUG: Global Sync command returned: {len(synced_commands)} commands. Names: {[cmd.name for cmd in synced_commands]}")
                log.info("GLOBAL slash command sync initiated (may take 10-60 minutes to appear).")
                # --- END GLOBAL SYNC TEST ---

                self.synced_guilds.add(self.user.id)
            except Exception as e:
                log.error(f"Failed to sync slash commands (outer catch): {e}", exc_info=True)

    async def on_command_error(self, ctx, error):
        from src.utils.error_handler import handle_command_error
        await handle_command_error(ctx, error)

nyxa_bot = NyxaBot()