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
        self.DAILY_REWARDS = game_settings.get("daily_rewards", {})
        logger.info(f"Daily rewards loaded: {self.DAILY_REWARDS}")

    @app_commands.command(name="inventory", description="View your currencies and other items.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
        
        if not user:
            await interaction.followup.send("❌ You haven't started your adventure yet. Use `/start`.")
            return
            
        embed = discord.Embed(title=f"🎒 {interaction.user.display_name}'s Inventory", color=discord.Color.dark_orange())
        embed.add_field(name="<:nyxies_icon:YOUR_ICON_ID> Nyxies", value=f"{user.nyxies:,}", inline=True)
        embed.add_field(name="<:moonglow_icon:YOUR_ICON_ID> Moonglow", value=f"{user.moonglow:,}", inline=True)
        embed.add_field(name="<:essence_icon:YOUR_ICON_ID> Essence", value=f"{user.essence:,}", inline=True)

        SHARDS_PER_AZURITE = 10 
        full_azurites = user.azurite_shards // SHARDS_PER_AZURITE
        remaining_shards = user.azurite_shards % SHARDS_PER_AZURITE
        azurite_display = f"<:azurite_icon:YOUR_ICON_ID> **{full_azurites}** Azurites\n<:shard_icon:YOUR_ICON_ID> **{remaining_shards}** Shards"
        
        embed.add_field(name="Summoning Energy", value=azurite_display, inline=False)
        embed.add_field(name="🎁 Loot Chests", value=f"{user.loot_chests:,}", inline=True)
        embed.set_footer(text="Use '/esprit collection' to see your Esprits.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="daily", description="Claim your daily bundle of resources.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                await interaction.followup.send(embed=discord.Embed(description="❌ You haven't started yet. Use `/start`.", color=discord.Color.red()))
                return

            now = datetime.utcnow()
            if user.last_daily_claim and (now - user.last_daily_claim) < timedelta(hours=22):
                remaining = timedelta(hours=22) - (now - user.last_daily_claim)
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                embed = discord.Embed(title="⏳ Already Claimed", description=f"You can claim your daily reward again in **{hours}h {minutes}m**.", color=discord.Color.red())
                await interaction.followup.send(embed=embed)
                return

            # Add all currencies from the config
            user.nyxies += self.DAILY_REWARDS.get("nyxies", 0)
            user.moonglow += self.DAILY_REWARDS.get("moonglow", 0)
            user.azurite_shards += self.DAILY_REWARDS.get("azurite_shards", 0)
            user.last_daily_claim = now
            session.add(user)
            await session.commit()
            
            # Build the description string for the rewards embed
            reward_desc = ""
            for currency, amount in self.DAILY_REWARDS.items():
                if amount > 0:
                    reward_desc += f"• **{amount:,}** {currency.replace('_', ' ').title()}\n"

            embed = discord.Embed(
                title="☀️ Daily Bundle Claimed!", 
                description=f"You received the following resources:\n{reward_desc}", 
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
    logger.info("✅ EconomyCog loaded")



