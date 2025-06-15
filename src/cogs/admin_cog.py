# src/cogs/admin_cog.py
from __future__ import annotations

import functools
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Literal, Optional, Tuple

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from sqlalchemy import func, select, and_
from sqlalchemy.orm import selectinload

from src.database.data_loader import EspritDataLoader
from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.cache_manager import CacheManager
from src.utils.logger import get_logger
from src.utils import transaction_logger # For admin action logging

# ─────────────────────────────────────────────────────────────────────────────
logger = get_logger(__name__)

# ─────────────────────────── utility decorator / helpers ─────────────────────
def owner_only(*, ephemeral: bool = True):
    """Decorator that ensures the caller is the bot owner & automatically defers."""
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(self: "AdminCog", interaction: discord.Interaction, *args, **kwargs):
            if not await self.bot.is_owner(interaction.user):
                return await interaction.response.send_message("❌ You are not the bot owner.", ephemeral=True)
            await interaction.response.defer(ephemeral=ephemeral)
            return await fn(self, interaction, *args, **kwargs)
        return wrapper
    return decorator

async def cog_autocomplete(interaction: discord.Interaction, current: str) -> List[Choice[str]]:
    """Autocomplete for reloading cogs."""
    return [
        Choice(name=ext, value=ext)
        for ext in interaction.client.extensions
        if current.lower() in ext.lower()
    ][:25]

# ────────────────────────────── main admin cog ──────────────────────────────
@app_commands.guild_only()
class AdminCog(commands.Cog):
    admin_group  = app_commands.Group(name="admin",  description="Core admin commands.")
    give_group   = app_commands.Group(name="give",   description="Give currency/items to a user.", parent=admin_group)
    remove_group = app_commands.Group(name="remove", description="Remove currency/items from a user.", parent=admin_group)
    set_group    = app_commands.Group(name="set",    description="Set an exact value for a user.", parent=admin_group)
    reset_group  = app_commands.Group(name="reset",  description="Reset data/cooldowns for a user.", parent=admin_group)
    list_group   = app_commands.Group(name="list",   description="List data for inspection.", parent=admin_group)
    reload_group = app_commands.Group(name="reload", description="Reload bot subsystems.", parent=admin_group)

    MODIFIABLE_ATTRIBUTES = (
        "faylen", "virelite", "fayrites", "fayrite_shards",
        "ethryl", "remna", "xp", "loot_chests", "level"
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache = CacheManager(default_ttl=300)

    # ─╢ shared attribute mutator (Now with locking and logging) ╟──────────────────
    async def _adjust(self, interaction: discord.Interaction, user: discord.User, attr: str, op: Literal["give", "remove", "set"], amount: int):
        """Shared logic for modifying a user's currency/attribute with safety checks."""
        if attr not in self.MODIFIABLE_ATTRIBUTES:
            return await interaction.followup.send("❌ Invalid attribute specified.", ephemeral=True)
        
        if op != "set" and amount < 0:
            return await interaction.followup.send("❌ Amount must be a positive number for 'give' or 'remove'.", ephemeral=True)

        async with get_session() as s:
            # RACE CONDITION FIX: Lock the user row for the duration of this transaction.
            u = await s.get(User, str(user.id), with_for_update=True)
            if not u:
                return await interaction.followup.send("❌ Target user has not started their journey (`/start`).", ephemeral=True)
            
            old_val = getattr(u, attr)
            
            if op == "give":
                new_val = old_val + amount
            elif op == "remove":
                new_val = max(0, old_val - amount)
            else: # 'set'
                new_val = amount
            
            setattr(u, attr, new_val)
            await s.commit()
            
        # AUDIT LOGGING: Log the admin action after it has been successfully committed.
        transaction_logger.log_admin_adjustment(
            interaction=interaction,
            target_user=user,
            attribute=attr,
            operation=op,
            amount=amount,
            old_value=old_val,
            new_value=new_val
        )
            
        verb = op.title()
        await interaction.followup.send(
            f"✅ **{verb}** successful for {user.mention}.\n"
            f"**{attr.replace('_',' ').title()}:** `{old_val:,}` → `{new_val:,}`",
            ephemeral=True
        )

    # ───────────────────────── CORE ADMIN commands ─────────────────────────
    @admin_group.command(name="stats", description="View global bot statistics.")
    @owner_only(ephemeral=False)
    async def admin_stats(self, interaction: discord.Interaction):
        # This function can be simplified and may not need caching depending on frequency of use.
        # For now, let's assume it's infrequent and calculate live.
        async with get_session() as s:
            stats = {
                "total_users": (await s.scalar(select(func.count(User.user_id)))) or 0,
                "total_esprits": (await s.scalar(select(func.count(UserEsprit.id)))) or 0,
                "total_faylen": (await s.scalar(select(func.sum(User.faylen)))) or 0,
            }

        embed = discord.Embed(title="📊 Bot Statistics", color=discord.Color.gold())
        embed.add_field(name="Total Users", value=f"{stats['total_users']:,}", inline=True)
        embed.add_field(name="Total Esprits Owned", value=f"{stats['total_esprits']:,}", inline=True)
        embed.add_field(name="Total Faylen in Economy", value=f"{stats['total_faylen']:,}", inline=True)
        embed.add_field(name="Server Count", value=f"{len(self.bot.guilds):,}", inline=True)
        
        await interaction.followup.send(embed=embed)

    @admin_group.command(name="inspect", description="Inspect a user’s full record.")
    @owner_only()
    async def inspect(self, interaction: discord.Interaction, user: discord.User):
        async with get_session() as s:
            u = await s.get(User, str(user.id))
            if not u:
                return await interaction.followup.send("❌ User has not registered with `/start`.", ephemeral=True)
            
            esprit_count = (await s.scalar(
                select(func.count(UserEsprit.id)).where(UserEsprit.owner_id == str(user.id))
            )) or 0
            
        embed = discord.Embed(title=f"🔍 Inspecting: {user.display_name}", color=discord.Color.dark_teal())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {u.user_id}")
        
        embed.add_field(name="Level & XP", value=f"Level **{u.level}** / **{u.level_cap}**\nXP: {u.xp:,}", inline=True)
        embed.add_field(name="Esprits", value=f"{esprit_count:,} owned", inline=True)
        embed.add_field(name="Pity", value=f"Standard: {u.pity_count_standard}\nPremium: {u.pity_count_premium}", inline=True)
        
        currencies = (
            f"💠 Faylen: `{u.faylen:,}`\n"
            f"🔷 Virelite: `{u.virelite:,}`\n"
            f"💎 Fayrites: `{u.fayrites:,}`\n"
            f"🔸 Shards: `{u.fayrite_shards:,}`\n"
            f"🔶 Ethryl: `{u.ethryl:,}`\n"
            f"🌀 Remna: `{u.remna:,}`"
        )
        embed.add_field(name="Currencies", value=currencies, inline=False)
        
        team_ids = [u.active_esprit_id, u.support1_esprit_id, u.support2_esprit_id]
        embed.add_field(name="Team IDs", value=f"L: `{team_ids[0]}`\nS1: `{team_ids[1]}`\nS2: `{team_ids[2]}`", inline=True)
        
        last_daily = f"<t:{int(u.last_daily_claim.timestamp())}:R>" if u.last_daily_claim else "Never"
        last_summon = f"<t:{int(u.last_daily_summon.timestamp())}:R>" if u.last_daily_summon else "Never"
        embed.add_field(name="Cooldowns", value=f"Daily Claim: {last_daily}\nDaily Summon: {last_summon}", inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ───────────────────────────── GIVE commands ───────────────────────────
    @give_group.command(name="currency", description="Give a specified currency to a user.")
    @owner_only()
    async def give_currency(self, interaction: discord.Interaction, user: discord.User, currency: Literal["faylen", "virelite", "fayrites", "fayrite_shards", "ethryl", "remna", "xp", "loot_chests"], amount: int):
        await self._adjust(interaction, user, currency, "give", amount)

    # ────────────────────────── REMOVE commands ───────────────────────────
    @remove_group.command(name="currency", description="Remove a specified currency from a user.")
    @owner_only()
    async def remove_currency(self, interaction: discord.Interaction, user: discord.User, currency: Literal["faylen", "virelite", "fayrites", "fayrite_shards", "ethryl", "remna", "xp", "loot_chests"], amount: int):
        await self._adjust(interaction, user, currency, "remove", amount)

    # ──────────────────────────── SET commands ────────────────────────────
    @set_group.command(name="currency", description="Set an exact currency amount for a user.")
    @owner_only()
    async def set_currency(self, interaction: discord.Interaction, user: discord.User, currency: Literal["faylen", "virelite", "fayrites", "fayrite_shards", "ethryl", "remna", "xp", "loot_chests"], amount: int):
        await self._adjust(interaction, user, currency, "set", amount)
        
    @set_group.command(name="level", description="Set a user's level.")
    @owner_only()
    async def set_level(self, interaction: discord.Interaction, user: discord.User, level: int):
        await self._adjust(interaction, user, "level", "set", level)

    # ─────────────────────────── RESET commands ───────────────────────────
    @reset_group.command(name="daily", description="Reset a user's /daily claim and summon cooldowns.")
    @owner_only()
    async def reset_daily(self, interaction: discord.Interaction, user: discord.User):
        async with get_session() as s:
            # RACE CONDITION FIX: Lock user row
            u = await s.get(User, str(user.id), with_for_update=True)
            if not u:
                return await interaction.followup.send("❌ User not registered.", ephemeral=True)
            u.last_daily_claim = None
            u.last_daily_summon = None
            await s.commit()
        await interaction.followup.send(f"✅ Daily claim and summon timers have been reset for {user.mention}.", ephemeral=True)

    # ─────────────────────────── RELOAD commands ───────────────────────────
    @reload_group.command(name="config", description="Reload all config files from disk.")
    @owner_only()
    async def reload_config(self, interaction: discord.Interaction):
        try:
            # Assuming self.bot.config_manager.reload() exists and works
            self.bot.config_manager.reload()
            logger.info(f"CONFIG RELOAD triggered by {interaction.user}")
            await interaction.followup.send("✅ All configuration files have been reloaded from disk.", ephemeral=True)
        except Exception as exc:
            logger.error("Configuration reload failed", exc_info=True)
            await interaction.followup.send(f"❌ **Failed to reload configs:**\n`{exc}`", ephemeral=True)

    @reload_group.command(name="cog", description="Reload a single bot cog.")
    @app_commands.autocomplete(cog_name=cog_autocomplete)
    @owner_only()
    async def reload_cog(self, interaction: discord.Interaction, cog_name: str):
        try:
            await self.bot.reload_extension(cog_name)
            logger.info(f"COG RELOAD: {cog_name} reloaded by {interaction.user}")
            await interaction.followup.send(f"✅ Successfully reloaded cog: `{cog_name}`", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to reload cog {cog_name}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error reloading `{cog_name}`:\n```py\n{traceback.format_exc(limit=1)}\n```",
                ephemeral=True
            )

    @reload_group.command(name="esprits", description="Reload Esprit static data from JSON into the database.")
    @owner_only()
    async def reload_esprits(self, interaction: discord.Interaction, force_update: bool = False):
        await interaction.followup.send("⏳ Reloading Esprit data... this may take a moment.", ephemeral=True)
        try:
            loader = EspritDataLoader()
            count = await loader.load_esprits(force_reload=force_update)
            missing = await loader.verify_data_integrity()
            
            message = f"✅ Loaded/Updated **{count:,}** esprit entries."
            if missing:
                message += f"\n⚠️ **{len(missing)}** Esprits from JSON are still missing from the database."
            
            await interaction.edit_original_response(content=message)
        except FileNotFoundError:
            await interaction.edit_original_response(content="❌ `esprits.json` not found in the expected directory.")
        except Exception as exc:
            logger.error("Failed to reload Esprit data", exc_info=True)
            await interaction.edit_original_response(content=f"❌ An unexpected error occurred: `{exc}`")

async def setup(bot: commands.Bot):
    cog = AdminCog(bot)
    bot.tree.add_command(cog.admin_group)
    await bot.add_cog(cog)
    logger.info("✅ AdminCog loaded")
