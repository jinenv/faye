import os
import sys
from dotenv import load_dotenv
import discord # Import discord to catch LoginFailure

# Add the project root to the Python path
# This ensures that imports like 'from src.bot import nyxa_bot' work correctly
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables from .env file
load_dotenv()

# Import the bot instance and logger after setting up sys.path and loading dotenv
from src.bot import nyxa_bot
from src.utils.logger import Logger

# Initialize main logger
log = Logger("main")

def main():
    """
    Main function to run the Nyxa Bot.
    """
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    if not DISCORD_BOT_TOKEN:
        log.critical("DISCORD_BOT_TOKEN not found in .env file. Please set it up.")
        return

    # Optional: Get TEST_GUILD_ID for faster slash command syncing in dev
    # (Uncomment this in src/bot.py for actual use)
    TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")
    if not TEST_GUILD_ID:
        log.warning("TEST_GUILD_ID not set in .env. Slash commands will only sync globally (slow).")

    log.info("Starting Nyxa Bot...")
    try:
        nyxa_bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        log.critical("Invalid bot token provided. Please check your DISCORD_BOT_TOKEN in .env.")
    except Exception as e:
        log.critical(f"An unexpected error occurred while running the bot: {e}", exc_info=True)

if __name__ == "__main__":
    main()