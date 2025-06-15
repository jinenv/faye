# src/cogs/economy_cog.py
from typing import Literal
import random
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta

from src.database.db import get_session
from src.database.models import User
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiter
from src.utils import transaction_logger

logger = get_logger(__name__)

DAILY_FLAVOR = [
    "🌬️ The winds of Faylen whisper your reward...",
    "✨ Faye smiles down upon you today.",
    "🔮 Aether currents flow in your favor.",
    "🌟 The stars align—gifts have arrived.",
    "🌙 Moonlight guides your fortune."
]

CURRENCY_ICONS = {
    "faylen": "💠",
    "virelite": "🔷",
    "ethryl": "🔶",
    "fayrites": "💎",
    "fayrite_shards": "🔸",
    "remna": "🌀",
    "loot_chests": "🎁"
}


class EconomyCog(commands.Cog):
    """Handles player economy commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.DAILY_REWARDS = game_settings.get("daily_rewards", {})
        self.cooldowns = game_settings.get("cooldowns", {})
        economy_settings = game_settings.get("economy", {})
        self.SHARDS_PER_FAYRITE = economy_settings.get("shards_per_fayrite", 10)
        self.general_limiter = RateLimiter(3, 20)
        self.daily_limiter = RateLimiter(3, 600)

        logger.info(f"✅ EconomyCog loaded. Daily rewards: {len(self.DAILY_REWARDS)} items.")

    @app_commands.command(name="inventory", description="View your currencies and other items.")
    async def inventory(self, interaction: discord.Interaction):
        # public by default
        await interaction.response.defer()
        if not await self.general_limiter.check(str(interaction.user.id)):
            return await interaction.followup.send("You're using commands too quickly!")

        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send("❌ You haven't started your adventure. Use `/start`.")

            embed = discord.Embed(
                title=f"🎒 {interaction.user.display_name}'s Inventory",
                color=discord.Color.dark_orange()
            )
            # Add each currency with icon
            for field in (
                ("faylen", user.faylen),
                ("virelite", user.virelite),
                ("ethryl", user.ethryl),
                ("fayrites", user.fayrites),
                ("fayrite_shards", user.fayrite_shards),
                ("remna", user.remna),
                ("loot_chests", user.loot_chests)
            ):
                icon = CURRENCY_ICONS.get(field[0], "")
                name = field[0].replace("_", " ").title()
                embed.add_field(name=f"{icon} {name}", value=f"{field[1]:,}", inline=True)

            embed.set_footer(text="Use `/esprit collection` to view your Esprits.")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="daily", description="Claim your daily bundle of resources.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await self.daily_limiter.check(str(interaction.user.id)):
            return await interaction.followup.send("You are trying to claim too frequently. Please wait.")

        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send("❌ You haven't started yet. Use `/start`.")

            cooldown_hours = self.cooldowns.get('daily_claim_hours', 22)
            now = datetime.utcnow()
            if user.last_daily_claim and now < user.last_daily_claim + timedelta(hours=cooldown_hours):
                remaining = (user.last_daily_claim + timedelta(hours=cooldown_hours)) - now
                h, rem = divmod(int(remaining.total_seconds()), 3600)
                m, _ = divmod(rem, 60)
                return await interaction.followup.send(
                    embed=discord.Embed(
                        title="⏳ Already Claimed",
                        description=f"Next claim in **{h}h {m}m**.",
                        color=discord.Color.red()
                    )
                )

            # Grant rewards
            for currency, amount in self.DAILY_REWARDS.items():
                if hasattr(user, currency):
                    setattr(user, currency, getattr(user, currency) + amount)
            user.last_daily_claim = now
            await session.commit()

            transaction_logger.log_daily_claim(logger, interaction, self.DAILY_REWARDS)

            reward_desc = "\n".join(
                f"{CURRENCY_ICONS.get(c, '')} **{amount:,}** {c.replace('_', ' ').title()}"
                for c, amount in self.DAILY_REWARDS.items() if amount > 0
            )
            embed = discord.Embed(
                title="☀️ Daily Bundle Claimed!",
                description=f"You received:\n{reward_desc}",
                color=discord.Color.green()
            )
            embed.set_footer(text=random.choice(DAILY_FLAVOR))
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="craft", description="Craft higher-tier items from materials.")
    @app_commands.describe(
        item="What to craft ('fayrite')",
        amount="Quantity, or 'all' to max"
    )
    async def craft(self, interaction: discord.Interaction, item: Literal['fayrite'], amount: str):
        await interaction.response.defer()
        if not await self.general_limiter.check(str(interaction.user.id)):
            return await interaction.followup.send("You're using commands too quickly!")

        if item.lower() != 'fayrite':
            return await interaction.followup.send("❌ You can only craft Fayrites.")

        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send("❌ You need to `/start` first.")

            needed = self.SHARDS_PER_FAYRITE
            if amount.lower() == 'all':
                max_craft = user.fayrite_shards // needed
                if max_craft < 1:
                    return await interaction.followup.send(f"❌ Need at least **{needed}** shards.")
                qty = max_craft
            else:
                try:
                    qty = int(amount)
                    if qty < 1:
                        raise ValueError()
                except ValueError:
                    return await interaction.followup.send("❌ Invalid amount. Use a number or 'all'.")

            cost = qty * needed
            if user.fayrite_shards < cost:
                return await interaction.followup.send(f"❌ Not enough shards. You need **{cost:,}**.")

            user.fayrite_shards -= cost
            user.fayrites += qty
            await session.commit()

            transaction_logger.log_craft_item(
                interaction,
                item_name="Fayrite",
                crafted_amount=qty,
                cost_str=f"{cost:,} Fayrite Shards"
            )

            embed = discord.Embed(
                title="✨ Crafting Complete!",
                description=(
                    f"💎 You forged **{qty:,}** Fayrite{'s' if qty>1 else ''} "
                    f"from **{cost:,}** Shards."
                ),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="New Balances",
                value=(
                    f"{CURRENCY_ICONS['fayrites']} **{user.fayrites:,}** Fayrite(s)\n"
                    f"{CURRENCY_ICONS['fayrite_shards']} **{user.fayrite_shards:,}** Shards"
                )
            )
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
    logger.info("✅ EconomyCog loaded")



