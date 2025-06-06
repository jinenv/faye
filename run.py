# run.py

import os
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from src.bot import main  # Import the main() entrypoint from src/bot.py

if __name__ == "__main__":
    BOT_TOKEN = os.getenv("DISCORD_TOKEN")
    if not BOT_TOKEN:
        print("Error: DISCORD_TOKEN not found in .env file.")
        exit(1)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot shutdown initiated by user.")
    except Exception as e:
        print(f"An error occurred during bot startup: {e}")