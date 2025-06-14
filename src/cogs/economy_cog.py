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
# --- 1. IMPORT THE NEW LOGGER ---
from src.utils import transaction_logger 

logger = get_logger(__name__)

class EconomyCog(commands.Cog):
    """Handles player economy commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.DAILY_REWARDS = game_settings.get("daily_rewards", {})
        self.cooldowns = game_settings.get("cooldowns", {}) # Load cooldowns
        
        economy_settings = game_settings.get("economy", {})
        self.SHARDS_PER_FAYRITE = economy_settings.get("shards_per_fayrite", 10)
        
        self.general_limiter = RateLimiter(3, 20)
        self.daily_limiter = RateLimiter(3, 600)

        logger.info(f"✅ EconomyCog loaded. Daily rewards: {len(self.DAILY_REWARDS)} items.")

    @app_commands.command(name="inventory", description="View your currencies and other items.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.general_limiter.check(interaction.user.id):
            return await interaction.followup.send("You're using commands too quickly!", ephemeral=True)

        async with get_session() as session:
            # Assuming interaction.user.id is a string, which is correct for discord IDs
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send("❌ You haven't started your adventure yet. Use `/start`.", ephemeral=True)
            
            embed = discord.Embed(title=f"🎒 {interaction.user.display_name}'s Inventory", color=discord.Color.dark_orange())
            embed.add_field(name="Faylen", value=f"{user.faylen:,}", inline=True)
            embed.add_field(name="Virelite", value=f"{user.virelite:,}", inline=True)
            embed.add_field(name="Ethryl", value=f"{user.ethryl:,}", inline=True)
            fayrite_display = (f"**{user.fayrites:,}** Fayrites\n"
                               f"**{user.fayrite_shards:,}** Shards")
            embed.add_field(name="Remna", value=f"{user.remna:,}", inline=True)
            embed.add_field(name="Summoning Energy", value=fayrite_display, inline=False)
            embed.add_field(name="🎁 Loot Chests", value=f"{user.loot_chests:,}", inline=True)
            embed.set_footer(text="Use '/esprit collection' to see your Esprits.")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="daily", description="Claim your daily bundle of resources.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.daily_limiter.check(interaction.user.id):
            return await interaction.followup.send("You are trying to claim your daily too frequently. Please wait a bit.", ephemeral=True)
            
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
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
            
            await session.commit()
            
            # --- 2. CALL THE TRANSACTION LOGGER ---
            transaction_logger.log_daily_claim(logger, interaction, self.DAILY_REWARDS)

            reward_desc = "\n".join([f"• **{amount:,}** {c.replace('_', ' ').title()}" for c, amount in self.DAILY_REWARDS.items() if amount > 0])
            embed = discord.Embed(title="☀️ Daily Bundle Claimed!", description=f"You received:\n{reward_desc}", color=discord.Color.green())
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="craft", description="Craft higher-tier items from materials.")
    @app_commands.describe(item="The item you want to craft.", amount="How many to craft. 'all' to craft as many as possible.")
    async def craft(self, interaction: discord.Interaction, item: Literal['fayrite'], amount: str):
        if item.lower() != 'fayrite':
            return await interaction.response.send_message("❌ You can only craft Fayrites right now.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        if not await self.general_limiter.check(interaction.user.id):
            return await interaction.followup.send("You're using commands too quickly! Please wait a moment.", ephemeral=True)
            
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send("❌ You need to `/start` first.", ephemeral=True)

            shards_needed_per_fayrite = self.SHARDS_PER_FAYRITE
            
            if amount.lower() == 'all':
                if user.fayrite_shards < shards_needed_per_fayrite:
                    return await interaction.followup.send(f"❌ You need at least **{shards_needed_per_fayrite}** shards.", ephemeral=True)
                amount_to_craft = user.fayrite_shards // shards_needed_per_fayrite
            else:
                try:
                    amount_to_craft = int(amount)
                    if amount_to_craft <= 0:
                        return await interaction.followup.send("❌ Please provide a positive number.", ephemeral=True)
                except ValueError:
                    return await interaction.followup.send("❌ Invalid amount. Use a number or 'all'.", ephemeral=True)

            total_shards_cost = amount_to_craft * shards_needed_per_fayrite
            if user.fayrite_shards < total_shards_cost:
                return await interaction.followup.send(f"❌ Not enough shards. You need **{total_shards_cost:,}**.", ephemeral=True)

            user.fayrite_shards -= total_shards_cost
            user.fayrites += amount_to_craft
            
            await session.commit()
            
            # --- 3. CALL THE TRANSACTION LOGGER ---
            transaction_logger.log_craft_item(
                logger,
                interaction,
                item_name="Fayrite",
                crafted_amount=amount_to_craft,
                cost_str=f"{total_shards_cost:,} Fayrite Shards"
            )

            embed = discord.Embed(
                title="✨ Crafting Successful!",
                description=f"You converted **{total_shards_cost:,}** Fayrite Shards into **{amount_to_craft:,}** <:fayrite:YOUR_ICON_ID> Fayrite(s).",
                color=discord.Color.blue()
            )
            embed.add_field(name="New Balance", value=f"Fayrites: **{user.fayrites:,}**\nShards: **{user.fayrite_shards:,}**")
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
    logger.info("✅ EconomyCog loaded")

