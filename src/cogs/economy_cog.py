# src/cogs/economy_cog.py
from typing import Literal
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
        
        # Load the conversion rate from the new 'economy' section
        economy_settings = game_settings.get("economy", {})
        self.SHARDS_PER_AZURITE = economy_settings.get("shards_per_azurite", 10) # Default for safety
        
        logger.info(f"Daily rewards loaded: {self.DAILY_REWARDS}")
        logger.info(f"Azurite conversion rate loaded: {self.SHARDS_PER_AZURITE}")

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

        # No more division/modulo! Just display the raw values from the database.
        azurite_display = (f"<:azurite_icon:YOUR_ICON_ID> **{user.azurites:,}** Azurites\n"
                           f"<:shard_icon:YOUR_ICON_ID> **{user.azurite_shards:,}** Shards")
        
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

    @app_commands.command(name="craft", description="Craft higher-tier items from materials.")
    @app_commands.describe(item="The item you want to craft.", amount="How many to craft. 'all' to craft as many as possible.")
    async def craft(self, interaction: discord.Interaction, item: Literal['azurite'], amount: str):
        if item.lower() != 'azurite':
            return await interaction.response.send_message("❌ You can only craft Azurites right now.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send("❌ You need to `/start` first.", ephemeral=True)

            shards_needed_per_azurite = self.SHARDS_PER_AZURITE
            
            if amount.lower() == 'all':
                if user.azurite_shards < shards_needed_per_azurite:
                     return await interaction.followup.send(f"❌ You need at least **{shards_needed_per_azurite}** shards to craft an Azurite.", ephemeral=True)
                amount_to_craft = user.azurite_shards // shards_needed_per_azurite
            else:
                try:
                    amount_to_craft = int(amount)
                    if amount_to_craft <= 0:
                        return await interaction.followup.send("❌ Please provide a positive number to craft.", ephemeral=True)
                except ValueError:
                    return await interaction.followup.send("❌ Invalid amount. Please specify a number or 'all'.", ephemeral=True)

            total_shards_cost = amount_to_craft * shards_needed_per_azurite

            if user.azurite_shards < total_shards_cost:
                return await interaction.followup.send(
                    f"❌ You don't have enough shards. You need **{total_shards_cost:,}** shards to craft **{amount_to_craft}** Azurite(s), but you only have **{user.azurite_shards:,}**.",
                    ephemeral=True
                )

            # Perform the conversion
            user.azurite_shards -= total_shards_cost
            user.azurites += amount_to_craft
            
            session.add(user)
            await session.commit()

            embed = discord.Embed(
                title="✨ Crafting Successful!",
                description=f"You converted **{total_shards_cost:,}** Azurite Shards into **{amount_to_craft:,}** <:azurite_icon:YOUR_ICON_ID> Azurite(s).",
                color=discord.Color.blue()
            )
            embed.add_field(name="New Balance", value=f"Azurites: **{user.azurites:,}**\nShards: **{user.azurite_shards:,}")
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
    logger.info("✅ EconomyCog loaded")

