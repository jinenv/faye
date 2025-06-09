# src/cogs/economy_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta

from src.database.db import get_session
from src.database.models import User
from src.utils.logger import get_logger

logger = get_logger(__name__)

class EconomyCog(commands.Cog):
    """Handles player economy commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.DAILY_NYXIES_REWARD = game_settings.get("daily_nyxies_reward", 100)
        logger.info(f"Daily Nyxies reward set to: {self.DAILY_NYXIES_REWARD}")

    @app_commands.command(name="inventory", description="View your currencies and other items.")
    async def inventory(self, interaction: discord.Interaction):
        """Displays a user's full currency and item inventory."""
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
        
        if not user:
            await interaction.followup.send("❌ You haven't started your adventure yet. Use `/start`.")
            return
            
        embed = discord.Embed(
            title=f"🎒 {interaction.user.display_name}'s Inventory", 
            color=discord.Color.dark_orange()
        )
        
        embed.add_field(name="<:nyxies_icon:YOUR_ICON_ID> Nyxies", value=f"{user.nyxies:,}", inline=True)
        embed.add_field(name="<:moonglow_icon:YOUR_ICON_ID> Moonglow", value=f"{user.moonglow:,}", inline=True)
        embed.add_field(name="<:essence_icon:YOUR_ICON_ID> Essence", value=f"{user.essence:,}", inline=True)

        SHARDS_PER_AZURITE = 10 
        full_azurites = user.azurite_shards // SHARDS_PER_AZURITE
        remaining_shards = user.azurite_shards % SHARDS_PER_AZURITE
        
        azurite_display = (
            f"<:azurite_icon:YOUR_ICON_ID> **{full_azurites}** Azurites\n"
            f"<:shard_icon:YOUR_ICON_ID> **{remaining_shards}** Shards"
        )
        
        embed.add_field(name="Summoning Energy", value=azurite_display, inline=False)
        embed.add_field(name="🎁 Loot Chests", value=f"{user.loot_chests:,}", inline=True)
        
        embed.set_footer(text="Use '/esprit collection' to see your Esprits.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="daily", description="Claim your daily Nyxies reward.")
    async def daily(self, interaction: discord.Interaction):
        """Allows a user to claim their daily Nyxies."""
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                await interaction.followup.send(embed=discord.Embed(description="❌ You haven't started yet. Use `/start`.", color=discord.Color.red()))
                return

            # --- FIX: Reverted to manual database check ---
            now = datetime.utcnow()
            # We use a 22-hour cooldown to be a bit lenient
            if user.last_daily_claim and (now - user.last_daily_claim) < timedelta(hours=22):
                remaining = timedelta(hours=22) - (now - user.last_daily_claim)
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                
                embed = discord.Embed(
                    title="⏳ Already Claimed",
                    description=f"You can claim your daily reward again in **{hours}h {minutes}m**.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return

            user.nyxies += self.DAILY_NYXIES_REWARD
            user.last_daily_claim = now # This line is critical and was missing before
            session.add(user)
            await session.commit()
            
            embed = discord.Embed(
                title="☀️ Daily Claimed", 
                description=f"You received **{self.DAILY_NYXIES_REWARD} Nyxies**!\nYour new balance is **{user.nyxies:,}**.", 
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
    
    # The separate error handler is no longer needed as the check is manual again.

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
    logger.info("✅ EconomyCog loaded")



