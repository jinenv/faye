# src/cogs/admin.py
import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio

# --- ADDED IMPORTS ---
from src.database.models import User, EspritData, UserEsprit # To import models for deletion
from sqlalchemy import delete # For the delete statement
from src.database.db import get_session, create_db_and_tables, populate_static_data # Ensure get_session is imported
# --- END ADDED ---

from src.utils.logger import get_logger

logger = get_logger(__name__)

class AdminConfirmView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=60)
        self.confirmed = False
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("You are not the bot owner!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.send_message("Database reset confirmed!", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.send_message("Database reset cancelled.", ephemeral=True)

# src/cogs/admin.py
# ... (rest of imports and AdminConfirmView) ...
class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reset_db", description="[OWNER ONLY] Deletes & recreates DB. Requires bot restart. Use with caution!") # <--- SHORTENED DESCRIPTION
    @commands.is_owner()
    async def reset_db(self, interaction: discord.Interaction):
        # ... (rest of the command logic) ...
        await interaction.response.defer(thinking=True, ephemeral=True)

        # Removed the os.path.exists(db_path) check as we're no longer deleting the file
        
        confirm_view = AdminConfirmView(owner_id=interaction.user.id)
        confirmation_message = await interaction.followup.send(
            "⚠️ **WARNING:** This will delete **all user data and game progress** (but not the database file itself)!\n"
            "Are you absolutely sure you want to clear all data and repopulate static Esprit data?",
            view=confirm_view,
            ephemeral=True
        )

        await confirm_view.wait()

        if confirm_view.confirmed:
            try:
                # Disable the view buttons after confirmation/cancellation
                for item in confirm_view.children:
                    item.disabled = True
                await confirmation_message.edit(view=confirm_view)

                async with get_session() as session: # <--- CRUCIAL: Get a session for DB ops
                    # Clear data from tables in reverse order of foreign key dependencies
                    logger.warning(f"Admin {interaction.user.id} confirmed database data clear.")
                    await session.execute(delete(UserEsprit)) # Delete user owned spirits first
                    await session.execute(delete(User))       # Then delete users
                    await session.execute(delete(EspritData)) # Then clear static esprit data
                    await session.commit() # Commit these deletions
                    logger.warning("All data cleared from UserEsprit, User, and EspritData tables.")

                # Repopulate static data (this will now always run as tables are empty)
                await populate_static_data() # This automatically uses a new session internally
                logger.info("Static EspritData repopulated after data clear.")

                await interaction.followup.send(
                    "Database data cleared and static Esprit data repopulated. **No bot restart required.**"
                )
            except Exception as e:
                logger.error(f"Admin {interaction.user.id} failed to clear_db_data: {e}", exc_info=True)
                await interaction.followup.send(f"Error clearing database data: {e}. Check logs.", ephemeral=True)
        else:
            # Disable the view buttons after confirmation/cancellation
            for item in confirm_view.children:
                item.disabled = True
            await confirmation_message.edit(view=confirm_view)
            await interaction.followup.send("Database reset cancelled.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))