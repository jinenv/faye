# src/cogs/economy_cog.py

import logging
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta

from sqlalchemy.future import select

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData

logger = logging.getLogger(__name__)

class EconomyCog(commands.Cog):
    """
    Handles currency-related commands:
      • /balance   → show gold & dust
      • /daily     → claim 100 gold once per 24h
      • /inventory → list owned Esprits
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Fixed daily reward amount
        self.DAILY_AMOUNT = 100

    # ────────────────────────────────────────────────────────────────────────────
    #    /balance COMMAND
    # ────────────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="balance",
        description="Check your current gold and dust."
    )
    async def balance(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # 1) Fetch the User row from the database
        async with get_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            user_obj = result.scalar_one_or_none()

        # 2) If the user hasn't registered yet, prompt them to /start
        if not user_obj:
            await interaction.response.send_message(
                "❌ You haven't started your adventure yet. Use `/start` to register first.",
                ephemeral=True
            )
            return

        # 3) Otherwise, show their gold and dust
        gold = user_obj.gold
        dust = user_obj.dust

        embed = discord.Embed(
            title="💰 Your Wallet",
            description=f"You have **{gold} gold** and **{dust} dust**.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


    @balance.error
    async def balance_error(self, interaction: discord.Interaction, error):
        logger.error(f"Error in /balance: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Unexpected error. Please try again later.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Unexpected error. Please try again later.", ephemeral=True
            )


    # ────────────────────────────────────────────────────────────────────────────
    #    /daily COMMAND
    # ────────────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="daily",
        description="Claim your daily 100 gold reward."
    )
    async def daily(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # 1) Fetch the User row
        async with get_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            user_obj = result.scalar_one_or_none()

            # 2) If not registered, prompt to /start
            if not user_obj:
                await interaction.response.send_message(
                    "❌ You haven't started your adventure yet. Use `/start` to register first.",
                    ephemeral=True
                )
                return

            # 3) Check last_daily_claim
            now = datetime.utcnow()
            last_claim = user_obj.last_daily_claim
            if last_claim:
                elapsed = now - last_claim
            else:
                elapsed = timedelta(days=999)  # Effectively "never claimed"

            # 4) If 24h haven't passed, tell them how long remains
            if elapsed < timedelta(hours=24):
                remaining = timedelta(hours=24) - elapsed
                hrs, rem = divmod(int(remaining.total_seconds()), 3600)
                mins, secs = divmod(rem, 60)
                embed = discord.Embed(
                    title="⏳ Already Claimed",
                    description=f"You can claim your next daily reward in **{hrs}h {mins}m {secs}s**.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # 5) Otherwise, grant reward and update last_daily_claim
            user_obj.gold += self.DAILY_AMOUNT
            user_obj.last_daily_claim = now
            session.add(user_obj)
            await session.commit()

            new_bal = user_obj.gold
            embed = discord.Embed(
                title="☀️ Daily Claimed",
                description=(
                    f"You received **{self.DAILY_AMOUNT} gold**!\n"
                    f"Your new balance is **{new_bal} gold**."
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


    @daily.error
    async def daily_error(self, interaction: discord.Interaction, error):
        logger.error(f"Error in /daily: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Unexpected error. Please try again later.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Unexpected error. Please try again later.", ephemeral=True
            )


    # ────────────────────────────────────────────────────────────────────────────
    #    /inventory COMMAND
    # ────────────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="inventory",
        description="View all Esprits you own."
    )
    async def inventory(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        async with get_session() as session:
            # 1) Check if the user exists
            stmt_user = select(User).where(User.user_id == user_id)
            result_user = await session.execute(stmt_user)
            user_obj = result_user.scalar_one_or_none()

            if not user_obj:
                await interaction.response.send_message(
                    "❌ You haven't started your adventure yet. Use `/start` to register first.",
                    ephemeral=True
                )
                return

            # 2) Fetch all UserEsprit rows for this user, joining EspritData to get names/rarities
            stmt = (
                select(UserEsprit, EspritData.name, EspritData.rarity)
                .join(EspritData, UserEsprit.esprit_data_id == EspritData.esprit_id)
                .where(UserEsprit.owner_id == user_id)
            )
            result = await session.execute(stmt)
            rows = result.all()

        # 3) If no Esprits, tell them so
        if not rows:
            embed = discord.Embed(
                title="📦 Your Inventory",
                description="You don’t own any Esprits yet.",
                color=discord.Color.light_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 4) Otherwise, build a list of “Name (Rarity)”
        lines = []
        for user_esprit, esprit_name, esprit_rarity in rows:
            lines.append(f"- **{esprit_name}** ({esprit_rarity})")

        desc = "\n".join(lines)
        embed = discord.Embed(
            title="📦 Your Inventory",
            description=desc,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


    @inventory.error
    async def inventory_error(self, interaction: discord.Interaction, error):
        logger.error(f"Error in /inventory: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Unexpected error. Please try again later.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Unexpected error. Please try again later.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))









