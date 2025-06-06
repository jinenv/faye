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
    """
    Admin‐only commands. Currently exposes:
      • /reset_db  → deletes all rows in UserEsprit, User, and EspritData,
                     then re‐creates the tables and re‐seeds static EspritData.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="reset_db",
        description="(Admin only) Wipe all users and Esprit data, then repopulate static data."
    )
    async def reset_db(self, interaction: discord.Interaction):
        # You may wish to add an actual admin‐check here
        # if not interaction.user.guild_permissions.administrator:
        #     return await interaction.response.send_message("You must be an administrator to use this.", ephemeral=True)

        try:
            # 1. Defer the response immediately since this can take time
            await interaction.response.defer(ephemeral=True, thinking=True)
            
            # 2. Perform all database operations
            async with get_session() as session:
                await session.execute(delete(UserEsprit))
                await session.execute(delete(User))
                await session.execute(delete(EspritData))
                await session.commit()

            await create_db_and_tables()
            await populate_static_data(self.bot.config_manager)

            # 3. Send the success message using followup
            await interaction.followup.send(
                "✅ Database has been wiped and static EspritData repopulated.",
                ephemeral=True
            )
            logger.warning(f"AdminCog: /reset_db called by {interaction.user.name} → tables wiped and EspritData re‐seeded.")
        
        except Exception as e:
            logger.error(f"Error in /reset_db: {e}", exc_info=True)
            # 4. Send the error message using followup
            # Check if the interaction is already responded to before sending another message
            if not interaction.is_done():
                 await interaction.response.send_message("❌ An error occurred while resetting the database.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred while resetting the database.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))