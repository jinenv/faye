# src/cogs/admin_cog.py
import logging
import discord
from discord.ext import commands
from discord import app_commands
from sqlmodel import delete

from src.database.db import get_session, create_db_and_tables, populate_static_data
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger

logger = get_logger(__name__)

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reset_db", description="(Admin only) Wipes and re-seeds the database.")
    async def reset_db(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            
            async with get_session() as session:
                await session.execute(delete(UserEsprit))
                await session.execute(delete(User))
                await session.execute(delete(EspritData))
                await session.commit()

            await create_db_and_tables()
            await populate_static_data(self.bot.config_manager)

            await interaction.followup.send("✅ Database has been wiped and re-seeded.", ephemeral=True)
            logger.warning(f"/reset_db called by {interaction.user.name}")
        
        except Exception as e:
            logger.error(f"Error in /reset_db: {e}", exc_info=True)
            # A simple follow-up is the most robust way to handle errors after deferring.
            if not interaction.is_done():
                await interaction.response.send_message("❌ An error occurred while resetting the database.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred while resetting the database.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))