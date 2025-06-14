import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager
from src.database.db import create_db_and_tables
from src.database.data_loader import EspritDataLoader

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
        # CRITICAL: Setup database and load Esprit data BEFORE loading cogs
        await self.setup_database()
        
        for cog in self.initial_cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Successfully loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}", exc_info=True)
        
        await self.tree.sync()
        logger.info("Synced slash commands globally.")

    async def setup_database(self):
        """Setup database tables and ensure Esprit data is loaded."""
        try:
            logger.info("Setting up database...")
            
            # Create all database tables
            await create_db_and_tables()
            logger.info("Database tables created/verified")
            
            # Load Esprit data from JSON
            loader = EspritDataLoader()
            missing = await loader.verify_data_integrity()
            
            if missing:
                logger.warning(f"Missing {len(missing)} Esprits in database, loading from JSON...")
                count = await loader.load_esprits(force_reload=False)
                logger.info(f"Successfully loaded {count} Esprits from esprits.json")
            else:
                logger.info("All Esprit data verified in database")
                
            # Final verification - ensure we have Epic Esprits for onboarding
            await self.verify_starter_esprits()
            
        except Exception as e:
            logger.critical(f"CRITICAL: Database setup failed: {e}", exc_info=True)
            raise RuntimeError("Database setup failed - bot cannot start safely") from e

    async def verify_starter_esprits(self):
        """Verify Epic Esprits exist for onboarding."""
        from sqlalchemy.future import select
        from src.database.db import get_session
        from src.database.models import EspritData
        
        async with get_session() as session:
            # Check for Epic rarity Esprits
            stmt = select(EspritData).where(EspritData.rarity == "Epic")
            result = await session.execute(stmt)
            epic_esprits = result.scalars().all()
            
            if not epic_esprits:
                logger.critical("CRITICAL: No Epic Esprits found! Onboarding will fail!")
                raise RuntimeError("No Epic Esprits available for starter system")
            
            logger.info(f"Verified {len(epic_esprits)} Epic Esprits available for onboarding")
            
            # Log available Epic Esprits for debugging
            epic_names = [esprit.name for esprit in epic_esprits]
            logger.info(f"Available Epic Esprits: {', '.join(epic_names)}")

    async def on_ready(self):
        """Called when the bot is ready and connected to Discord."""
        logger.info(f"Logged in as {self.user.name} (ID: {self.user.id})")
        logger.info("Nyxa is now online and ready.")

async def main():
    """The main entry point for the bot."""
    bot = NyxaBot()
    
    if not DISCORD_BOT_TOKEN:
        logger.critical("DISCORD_BOT_TOKEN not found in environment variables. Bot cannot start.")
        return
    
    try:
        await bot.start(DISCORD_BOT_TOKEN)
    except Exception as e:
        logger.critical(f"Bot startup failed: {e}", exc_info=True)

def run_bot():
    """Synchronous wrapper to run the async main function."""
    import asyncio
    asyncio.run(main())

if __name__ == "__main__":
    run_bot()
