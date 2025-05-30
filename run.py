# run.py
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import the bot instance directly from src.bot
# This assumes src.bot.py creates an instance named 'nyxa_bot'
from src.bot import nyxa_bot

# Get the bot token from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found in .env file.")
        return

    # Start the bot
    await nyxa_bot.start(BOT_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot shutdown initiated by user.")
    except Exception as e:
        print(f"An error occurred during bot startup: {e}")