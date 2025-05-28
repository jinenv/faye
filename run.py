import os
import sys

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"DEBUG: sys.path includes: {sys.path}")

from dotenv import load_dotenv
from src.bot import nyxa_bot
from src.utils.logger import Logger
import discord # Make sure discord is imported here for discord.LoginFailure

# Load environment variables (ensure this is at the very top for setup)
load_dotenv()

# Initialize root logger
log = Logger("main")

def main():
    """
    Main function to run the Project X Discord bot.
    """
    # Get the Discord bot token from environment variables
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    if not DISCORD_BOT_TOKEN:
        log.critical("DISCORD_BOT_TOKEN not found in .env file. Please set it up.")
        return

    # Get optional TEST_GUILD_ID for faster slash command syncing in dev
    TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")
    if not TEST_GUILD_ID:
        log.warning("TEST_GUILD_ID not set in .env. Slash commands will only sync globally (slow).")

    log.info("Starting Project X Bot...")
    try:
        nyxa_bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure: # This is why import discord is needed
        log.critical("Invalid bot token provided. Please check your DISCORD_BOT_TOKEN in .env.")
    except Exception as e:
        log.critical(f"An unexpected error occurred while running the bot: {e}", exc_info=True)

if __name__ == "__main__":
    main()