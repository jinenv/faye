# src/cogs/economy_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from sqlalchemy.future import select

from src.database.db import get_session
from src.database.models import User
from src.utils.logger import get_logger

logger = get_logger(__name__)

class EconomyCog(commands.Cog):
    """Handles player economy commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.DAILY_AMOUNT = game_settings.get("daily_summon_cost", 100)

    @app_commands.command(name="balance", description="Check your current gold balance.")
    async def balance(self, interaction: discord.Interaction):
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
        if not user:
            return await interaction.response.send_message("❌ You haven't started your adventure yet. Use `/start`.", ephemeral=True)
        
        embed = discord.Embed(title="💰 Gold Balance", description=f"You have **{user.gold:,} gold**.", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="inventory", description="View your currencies and other items.")
    async def inventory(self, interaction: discord.Interaction):
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
        if not user:
            return await interaction.response.send_message("❌ You haven't started your adventure yet. Use `/start`.", ephemeral=True)
            
        embed = discord.Embed(title="📦 Inventory", color=discord.Color.dark_orange())
        embed.add_field(name="✨ Dust", value=f"{user.dust:,}", inline=True)
        embed.add_field(name="💎 Fragments", value=f"{user.fragments:,}", inline=True)
        embed.add_field(name="🎁 Loot Chests", value=f"{user.loot_chests:,}", inline=True)
        embed.set_footer(text="Use '/esprit collection' to see your Esprits.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="daily", description="Claim your daily gold reward.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                await interaction.followup.send(embed=discord.Embed(description="❌ You haven't started yet. Use `/start`.", color=discord.Color.red()))
                return

            now = datetime.utcnow()
            if user.last_daily_claim and (now - user.last_daily_claim) < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - user.last_daily_claim)
                await interaction.followup.send(embed=discord.Embed(title="⏳ Already Claimed", description=f"Next claim in **{str(remaining).split('.')[0]}**.", color=discord.Color.red()))
                return

            user.gold += self.DAILY_AMOUNT
            user.last_daily_claim = now
            session.add(user)
            await session.commit()
            
            embed = discord.Embed(title="☀️ Daily Claimed", description=f"You received **{self.DAILY_AMOUNT} gold**!\nYour new balance is **{user.gold:,} gold**.", color=discord.Color.green())
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
    logger.info("✅ EconomyCog loaded")




