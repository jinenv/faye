# src/cogs/economy_cog.py
from typing import Literal
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta

from src.database.db import get_session
from src.database.models import User
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiter

logger = get_logger(__name__)

class EconomyCog(commands.Cog):
    """Handles player economy commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.DAILY_REWARDS = game_settings.get("daily_rewards", {})
        self.cooldowns = game_settings.get("cooldowns", {}) # Load cooldowns
        
        economy_settings = game_settings.get("economy", {})
        self.SHARDS_PER_AZURITE = economy_settings.get("shards_per_azurite", 10)
        
        self.general_limiter = RateLimiter(3, 20)
        self.daily_limiter = RateLimiter(3, 600)

        logger.info(f"✅ EconomyCog loaded. Daily rewards: {len(self.DAILY_REWARDS)} items.")

    @app_commands.command(name="inventory", description="View your currencies and other items.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.general_limiter.check(interaction.user.id):
            return await interaction.followup.send("You're using commands too quickly!", ephemeral=True)

        async with get_session() as session:
            user = await session.get(User, interaction.user.id)
            if not user:
                return await interaction.followup.send("❌ You haven't started your adventure yet. Use `/start`.", ephemeral=True)
            
            embed = discord.Embed(title=f"🎒 {interaction.user.display_name}'s Inventory", color=discord.Color.dark_orange())
            embed.add_field(name="<:nyxies:YOUR_ICON_ID> Nyxies", value=f"{user.nyxies:,}", inline=True)
            embed.add_field(name="<:moonglow:YOUR_ICON_ID> Moonglow", value=f"{user.moonglow:,}", inline=True)
            embed.add_field(name="<:aether:YOUR_ICON_ID> Aether", value=f"{user.aether:,}", inline=True)
            azurite_display = (f"<:azurite:YOUR_ICON_ID> **{user.azurites:,}** Azurites\n"
                               f"<:shard:YOUR_ICON_ID> **{user.azurite_shards:,}** Shards")
            embed.add_field(name="<:essence:YOUR_ICON_ID> Essence", value=f"{user.essence:,}", inline=True)
            embed.add_field(name="Summoning Energy", value=azurite_display, inline=False)
            embed.add_field(name="🎁 Loot Chests", value=f"{user.loot_chests:,}", inline=True)
            embed.set_footer(text="Use '/esprit collection' to see your Esprits.")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="daily", description="Claim your daily bundle of resources.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.daily_limiter.check(interaction.user.id):
            return await interaction.followup.send("You are trying to claim your daily too frequently. Please wait a bit.", ephemeral=True)
            
        async with get_session() as session:
            user = await session.get(User, interaction.user.id)
            if not user:
                return await interaction.followup.send(embed=discord.Embed(description="❌ You haven't started yet. Use `/start`.", color=discord.Color.red()))

            cooldown_hours = self.cooldowns.get('daily_claim_hours', 22)
            now = datetime.utcnow()
            
            if user.last_daily_claim and (now < user.last_daily_claim + timedelta(hours=cooldown_hours)):
                remaining = timedelta(hours=cooldown_hours) - (now - user.last_daily_claim)
                hours, rem = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(rem, 60)
                embed = discord.Embed(title="⏳ Already Claimed", description=f"You can claim your daily reward again in **{hours}h {minutes}m**.", color=discord.Color.red())
                return await interaction.followup.send(embed=embed)

            # Grant rewards
            for currency, amount in self.DAILY_REWARDS.items():
                if hasattr(user, currency):
                    setattr(user, currency, getattr(user, currency) + amount)
            user.last_daily_claim = now
            
            # --- FIX: SAVE THE CHANGES TO THE DATABASE ---
            await session.commit()
            
            reward_desc = "\n".join([f"• **{amount:,}** {c.replace('_', ' ').title()}" for c, amount in self.DAILY_REWARDS.items() if amount > 0])
            embed = discord.Embed(title="☀️ Daily Bundle Claimed!", description=f"You received:\n{reward_desc}", color=discord.Color.green())
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="craft", description="Craft higher-tier items from materials.")
    @app_commands.describe(item="The item you want to craft.", amount="How many to craft. 'all' to craft as many as possible.")
    async def craft(self, interaction: discord.Interaction, item: Literal['azurite'], amount: str):
        if item.lower() != 'azurite':
            return await interaction.response.send_message("❌ You can only craft Azurites right now.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        if not await self.general_limiter.check(interaction.user.id):
            return await interaction.followup.send("You're using commands too quickly! Please wait a moment.", ephemeral=True)
            
        async with get_session() as session:
            user = await session.get(User, interaction.user.id)
            if not user:
                return await interaction.followup.send("❌ You need to `/start` first.", ephemeral=True)

            shards_needed_per_azurite = self.SHARDS_PER_AZURITE
            
            if amount.lower() == 'all':
                if user.azurite_shards < shards_needed_per_azurite:
                    return await interaction.followup.send(f"❌ You need at least **{shards_needed_per_azurite}** shards.", ephemeral=True)
                amount_to_craft = user.azurite_shards // shards_needed_per_azurite
            else:
                try:
                    amount_to_craft = int(amount)
                    if amount_to_craft <= 0:
                        return await interaction.followup.send("❌ Please provide a positive number.", ephemeral=True)
                except ValueError:
                    return await interaction.followup.send("❌ Invalid amount. Use a number or 'all'.", ephemeral=True)

            total_shards_cost = amount_to_craft * shards_needed_per_azurite
            if user.azurite_shards < total_shards_cost:
                return await interaction.followup.send(f"❌ Not enough shards. You need **{total_shards_cost:,}**.", ephemeral=True)

            user.azurite_shards -= total_shards_cost
            user.azurites += amount_to_craft
            
            # --- FIX: SAVE THE CHANGES TO THE DATABASE ---
            await session.commit()

            embed = discord.Embed(
                title="✨ Crafting Successful!",
                description=f"You converted **{total_shards_cost:,}** Azurite Shards into **{amount_to_craft:,}** <:azurite:YOUR_ICON_ID> Azurite(s).",
                color=discord.Color.blue()
            )
            embed.add_field(name="New Balance", value=f"Azurites: **{user.azurites:,}**\nShards: **{user.azurite_shards:,}**")
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
    logger.info("✅ EconomyCog loaded")

