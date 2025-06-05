# src/cogs/admin.py

import discord
from discord.ext import commands
from discord import app_commands
import os
import json

from src.database.models import User, EspritData, UserEsprit
from sqlalchemy import delete
from src.database.db import get_session, populate_static_data

from src.utils.logger import get_logger
from src.utils.economy_manager import EconomyManager
from src.utils.inventory_manager import InventoryManager

logger = get_logger(__name__)


class AdminConfirmView(discord.ui.View):
    """
    A simple confirm/cancel view. Only the owner may click.
    """

    def __init__(self, owner_id: int):
        super().__init__(timeout=60)
        self.confirmed = False
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "🚫 You are not authorized to do this.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="⚠️ Confirm Full Reset",
        style=discord.ButtonStyle.danger,
        custom_id="confirm_full_reset"
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.confirmed = True
        self.stop()
        await interaction.response.send_message(
            "✅ Reset confirmed. Clearing all data…", ephemeral=True
        )

    @discord.ui.button(
        label="❌ Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="cancel_full_reset"
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.confirmed = False
        self.stop()
        await interaction.response.send_message(
            "✋ Aborted. No data was changed.", ephemeral=True
        )


class Admin(commands.Cog):
    """
    Admin utilities: /reset_db completely wipes:
      • economy JSON (gold & dust)
      • inventory JSON (owned Esprits)
      • SQL tables (UserEsprit, User, EspritData)
      • Then repopulates EspritData from static config
      • Finally, forces all other cogs to recreate their economy/inventory managers
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # **Make sure these paths match exactly** the ones used by your managers elsewhere.
        self.economy_path   = os.path.join("data", "economy.json")
        self.inventory_path = os.path.join("data", "inventory.json")

    @app_commands.command(
        name="reset_db",
        description="[OWNER ONLY] Wipes ALL user data (JSON + SQL)."
    )
    @commands.is_owner()
    async def reset_db(self, interaction: discord.Interaction):
        """
        Slash command for the bot owner only. Prompts for confirmation.
        On confirm:
          1) Overwrite economy.json -> {}
          2) Overwrite inventory.json -> {}
          3) Truncate UserEsprit, User, EspritData tables
             -> then call populate_static_data()
          4) For every cog that holds an EconomyManager/InventoryManager,
             replace those instances with fresh ones so they read the now-empty JSON.
        """

        # 0) Defer so we can follow up
        await interaction.response.defer(thinking=True, ephemeral=True)

        # 1) Ask for confirmation
        view = AdminConfirmView(owner_id=interaction.user.id)
        warning_embed = discord.Embed(
            title="🛑 Confirm FULL Data Reset",
            description=(
                "This will **DELETE ALL USER PROGRESS** and leave you with a fresh development slate.\n\n"
                "• `economy.json` (gold & dust) → will become `{}`\n"
                "• `inventory.json` (owned Esprits) → will become `{}`\n"
                "• SQL Tables:\n"
                "    • `UserEsprit` → all rows deleted\n"
                "    • `User` → all rows deleted\n"
                "    • `EspritData` → all rows deleted, then re‐populated from static config\n\n"
                "Press **⚠️ Confirm Full Reset** to proceed, or **❌ Cancel** to abort."
            ),
            color=discord.Color.red()
        )
        confirmation_msg = await interaction.followup.send(
            embed=warning_embed, view=view, ephemeral=True
        )

        # Wait up to 60 seconds
        await view.wait()

        # 2) If not confirmed, abort
        if not view.confirmed:
            for child in view.children:
                child.disabled = True
            await confirmation_msg.edit(view=view)
            return await interaction.followup.send(
                "❌ Reset aborted. No data was changed.", ephemeral=True
            )

        # 3) Proceed with wiping JSON and SQL
        await interaction.followup.send(
            "⚙️ Resetting all data now… please stand by.", ephemeral=True
        )

        # —— PART A: Overwrite JSON files —— 

        # A1) Clear economy.json
        try:
            os.makedirs(os.path.dirname(self.economy_path), exist_ok=True)
            with open(self.economy_path, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4)
            logger.warning("economy.json successfully cleared.")
        except Exception as e:
            logger.error(f"Failed to clear economy.json: {e}", exc_info=True)

        # A2) Clear inventory.json
        try:
            os.makedirs(os.path.dirname(self.inventory_path), exist_ok=True)
            with open(self.inventory_path, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4)
            logger.warning("inventory.json successfully cleared.")
        except Exception as e:
            logger.error(f"Failed to clear inventory.json: {e}", exc_info=True)

        # —— PART B: Truncate SQL Tables —— 

        try:
            async with get_session() as session:
                # Delete from dependent tables first
                await session.execute(delete(UserEsprit))
                await session.execute(delete(User))
                # Now delete the static EspritData
                await session.execute(delete(EspritData))
                await session.commit()
                logger.warning("SQL tables UserEsprit, User, EspritData wiped.")
        except Exception as e_db:
            logger.error(f"Error wiping SQL tables: {e_db}", exc_info=True)

        # —— PART C: Repopulate EspritData —— 

        try:
            await populate_static_data()
            logger.info("EspritData re‐populated from static config.")
        except Exception as e_pop:
            logger.error(f"Error re‐populating EspritData: {e_pop}", exc_info=True)

        # —— PART D: Replace Managers In Every Cog —— 

        # We know SummonCog holds .economy and .inventory. If you have other cogs that keep a manager,
        # add them here as well.
        failed_replacements = []

        # Attempt to replace the managers inside SummonCog
        summon_cog = self.bot.get_cog("SummonCog")
        if summon_cog is not None:
            try:
                summon_cog.economy = EconomyManager(self.economy_path)
                summon_cog.inventory = InventoryManager(self.inventory_path)
                logger.info("SummonCog: economy & inventory managers reloaded from empty JSON.")
            except Exception as e:
                failed_replacements.append(f"SummonCog: {e}")
        else:
            logger.warning("SummonCog not found—could not reload its managers.")

        # If you have any other cogs that hold EconomyManager/InventoryManager, do the same:
        # e.g. profile_cog = self.bot.get_cog("ProfileCog")
        #       if profile_cog: profile_cog.economy = EconomyManager(self.economy_path)
        #                      profile_cog.inventory = InventoryManager(self.inventory_path)

        # 4) Disable buttons and finalize
        for child in view.children:
            child.disabled = True
        await confirmation_msg.edit(view=view)

        # If replacements failed, show a warning; otherwise, success:
        if failed_replacements:
            desc = "Reset completed, but failed to reload managers in:\n" + "\n".join(failed_replacements)
            footer = "Check logs for details."
            color = discord.Color.orange()
        else:
            desc = (
                "- economy.json cleared\n"
                "- inventory.json cleared\n"
                "- SQL tables UserEsprit & User truncated\n"
                "- SQL table EspritData truncated & re‐populated\n"
                "- SummonCog’s managers reloaded from empty JSON\n\n"
                "**No bot restart required.**"
            )
            footer = None
            color = discord.Color.green()

        success_embed = discord.Embed(
            title="✅ FULL DATA RESET COMPLETE",
            description=desc,
            color=color
        )
        if footer:
            success_embed.set_footer(text=footer)

        await interaction.followup.send(embed=success_embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
