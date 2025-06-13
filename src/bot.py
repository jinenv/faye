import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager # <--- IMPORT IT

logger = get_logger(__name__)

# Load environment variables
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN")

class NyxaBot(commands.Bot):
    """The main bot class for Nyxa."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        # --- CREATE AND ATTACH THE CONFIG MANAGER ---
        self.config_manager = ConfigManager()

        self.initial_cogs = [
            "src.cogs.admin_cog",
            "src.cogs.economy_cog",
            "src.cogs.esprit_cog",
            "src.cogs.help_cog",
            "src.cogs.onboarding_cog",
            "src.cogs.summon_cog",
            "src.cogs.utility_cog",
        ]

    async def setup_hook(self):
        """Load all initial cogs and sync commands globally."""
        for cog in self.initial_cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Successfully loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}", exc_info=True)
        
        await self.tree.sync()
        logger.info("Synced slash commands globally.")


    async def on_ready(self):
        """Called when the bot is ready and connected to Discord."""
        logger.info(f"Logged in as {self.user.name} (ID: {self.user.id})")
        logger.info("Nyxa is now online and ready.")

def main():
    """The main entry point for the bot."""
    bot = NyxaBot()
    if not DISCORD_BOT_TOKEN:
        logger.critical("DISCORD_BOT_TOKEN not found in environment variables. Bot cannot start.")
        return
        
    bot.run(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()

