import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables (ensure this is done before accessing os.getenv)
load_dotenv()

# Import the logger
from src.utils.logger import Logger
log = Logger(__name__)

class NyxaBot(commands.Bot):
    def __init__(self):
        # Define the intents your bot needs.
        # Intents are a way to tell Discord which events your bot wants to receive.
        # discord.Intents.default() provides a good starting set.
        # intents.members is needed for member-related events (e.g., username access).
        # intents.message_content is crucial for reading message content, especially for prefix commands.
        intents = discord.Intents.default()
        intents.members = True          # Required for member cache and some member-related events
        intents.message_content = True  # Required to read message content for prefix commands

        # Initialize the bot with a command prefix and intents.
        # commands.when_mentioned_or("!") means commands can start with "!", or by mentioning the bot.
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)

        # Track synced guilds to avoid re-syncing global commands unnecessarily.
        self.synced_guilds = set()
        # Define initial cogs to load when the bot starts.
        # For now, we are starting with an empty list. We will add cogs as we build them.
        self.initial_cogs = []

    async def setup_hook(self):
        """
        Called once the bot is ready to start connecting to Discord.
        This is where you'd typically load extensions (cogs) and set up databases.
        """
        log.info("Running setup_hook...")

        # We will load cogs here as we implement them. For now, this loop is empty.
        for cog in self.initial_cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Successfully loaded cog: {cog}")
            except Exception as e:
                log.error(f"Failed to load cog {cog}: {e}", exc_info=True)

        # We need to import the database setup here because it might depend on models
        # that are still being defined in other files, and to avoid circular imports
        # if other modules import db.py early.
        # We'll create src/database/db.py in the next step.
        from src.database.db import create_db_and_tables # Import db.py after other setup
        try:
            await create_db_and_tables()
            log.info("Database initialized and tables created.")
        except Exception as e:
            log.critical(f"Failed to initialize database: {e}", exc_info=True)


        # Add a simple test sync command for initial debugging
        @self.tree.command(name="testsync", description="A direct test command for troubleshooting slash command sync.")
        async def testsync_command(interaction: discord.Interaction):
            await interaction.response.send_message("Test sync successful!", ephemeral=True)
            log.info(f"User {interaction.user.id} used /testsync command.")
        log.info("DEBUG: Added direct '/testsync' command to bot.tree for diagnostic.")

        # If we need to sync commands during development, we can do it here.
        # Global sync can take up to an hour. Guild sync is instant.
        TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")
        if TEST_GUILD_ID:
            try:
                guild = discord.Object(id=int(TEST_GUILD_ID))
                # To clear previous commands in a test guild (useful for rapid dev):
                # await self.tree.clear_commands(guild=guild)
                # log.info(f"DEBUG: Cleared commands for test guild {TEST_GUILD_ID}.")

                synced_commands = await self.tree.sync(guild=guild)
                log.info(f"Synced {len(synced_commands)} slash commands to test guild: {TEST_GUILD_ID}. Names: {[cmd.name for cmd in synced_commands]}")
                self.synced_guilds.add(guild.id)
            except Exception as e:
                log.error(f"Failed to sync slash commands to test guild {TEST_GUILD_ID}: {e}", exc_info=True)
        else:
            # If no test guild is specified, try global sync
            log.info("Attempting GLOBAL slash command sync (may take 10-60 minutes to appear)...")
            synced_commands = await self.tree.sync() # Global sync
            log.info(f"Global Sync returned {len(synced_commands)} commands. Names: {[cmd.name for cmd in synced_commands]}")
            self.synced_guilds.add("global") # Mark global as synced (arbitrary indicator)


    async def on_ready(self):
        """
        Called when the bot successfully connects to Discord.
        """
        if not hasattr(self, 'uptime'):
            self.uptime = discord.utils.utcnow()

        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info("Bot is ready and online!")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """
        Global error handler for all commands.
        """
        # We'll create src/utils/error_handler.py in a later step.
        from src.utils.error_handler import handle_command_error
        await handle_command_error(ctx, error)

# Create an instance of the bot
nyxa_bot = NyxaBot()