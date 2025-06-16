# src/cogs/admin_cog.py
from __future__ import annotations

import functools
import traceback
from typing import List, Literal, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from sqlalchemy import func, select

from src.database.data_loader import EspritDataLoader
from src.database.db import get_session
from src.database.models import User, UserEsprit
from src.utils.logger import get_logger
from src.utils import transaction_logger

logger = get_logger(__name__)

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
    cogs = getattr(interaction.client, 'initial_cogs', [])
    return [
        Choice(name=ext, value=ext)
        for ext in cogs
        if current.lower() in ext.lower()
    ][:25]

@app_commands.guild_only()
class AdminCog(commands.Cog):
    admin_group  = app_commands.Group(name="admin",  description="Core admin commands.")
    give_group   = app_commands.Group(name="give",   description="Give currency/items to a user.", parent=admin_group)
    remove_group = app_commands.Group(name="remove", description="Remove currency/items from a user.", parent=admin_group)
    set_group    = app_commands.Group(name="set",    description="Set an exact value for a user.", parent=admin_group)
    reset_group  = app_commands.Group(name="reset",  description="Reset data/cooldowns for a user.", parent=admin_group)
    reload_group = app_commands.Group(name="reload", description="Reload bot subsystems.", parent=admin_group)

    MODIFIABLE_ATTRIBUTES = (
        "faylen", "virelite", "fayrites", "fayrite_shards",
        "ethryl", "remna", "xp", "loot_chests", "level", "level_cap"
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _adjust(self, interaction: discord.Interaction, user: discord.User, attr: str, op: Literal["give", "remove", "set"], amount: int):
        if attr not in self.MODIFIABLE_ATTRIBUTES:
            return await interaction.followup.send("❌ Invalid attribute specified.", ephemeral=True)
        
        if op != "set" and amount < 0:
            return await interaction.followup.send("❌ Amount must be positive for 'give' or 'remove'.", ephemeral=True)

        async with get_session() as s:
            u = await s.get(User, str(user.id), with_for_update=True)
            if not u:
                return await interaction.followup.send(f"❌ User {user.mention} has not registered with `/start`.", ephemeral=True)
            
            old_val = getattr(u, attr, 0)
            
            if op == "give": new_val = old_val + amount
            elif op == "remove": new_val = max(0, old_val - amount)
            else: new_val = amount
            
            setattr(u, attr, new_val)
            await s.commit()
            
        transaction_logger.log_admin_adjustment(
            interaction=interaction, target_user=user, attribute=attr,
            operation=op, amount=amount, old_value=old_val, new_value=new_val)
            
        await interaction.followup.send(
            f"✅ **{op.title()}** for {user.mention}: **{attr.replace('_',' ').title()}** `{old_val:,}` → `{new_val:,}`",
            ephemeral=True)

    @admin_group.command(name="inspect", description="Inspect a user’s full record.")
    @owner_only()
    async def inspect(self, interaction: discord.Interaction, user: discord.User):
        async with get_session() as s:
            u = await s.get(User, str(user.id))
            if not u: return await interaction.followup.send("❌ User has not registered.", ephemeral=True)
            esprit_count = (await s.scalar(select(func.count(UserEsprit.id)).where(UserEsprit.owner_id == str(user.id)))) or 0
            
        embed = discord.Embed(title=f"🔍 Inspecting: {user.display_name}", color=discord.Color.dark_teal())
        embed.set_thumbnail(url=user.display_avatar.url).set_footer(text=f"User ID: {u.user_id}")
        embed.add_field(name="Level & XP", value=f"Level **{u.level}** / **{u.level_cap}**\nXP: {u.xp:,}", inline=True)
        embed.add_field(name="Esprits", value=f"{esprit_count:,} owned", inline=True)
        embed.add_field(name="Pity", value=f"Standard: {u.pity_count_standard}\nPremium: {u.pity_count_premium}", inline=True)
        
        currencies = "\n".join([f"**{attr.title()}:** `{getattr(u, attr, 0):,}`" for attr in self.MODIFIABLE_ATTRIBUTES if 'fay' in attr or 'ethryl' in attr or 'remna' in attr])
        embed.add_field(name="Currencies", value=currencies, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @give_group.command(name="currency", description="Give a specified currency/attribute to a user.")
    @app_commands.describe(user="The user to give currency to.", currency="The currency to give.", amount="The amount to give.")
    @owner_only()
    async def give_currency(self, interaction: discord.Interaction, user: discord.User, currency: Literal["faylen", "virelite", "fayrites", "fayrite_shards", "ethryl", "remna", "xp", "loot_chests"], amount: int):
        await self._adjust(interaction, user, currency, "give", amount)

    @remove_group.command(name="currency", description="Remove a specified currency/attribute from a user.")
    @owner_only()
    async def remove_currency(self, interaction: discord.Interaction, user: discord.User, currency: Literal["faylen", "virelite", "fayrites", "fayrite_shards", "ethryl", "remna", "xp", "loot_chests"], amount: int):
        await self._adjust(interaction, user, currency, "remove", amount)

    @set_group.command(name="attribute", description="Set an exact attribute amount for a user.")
    @owner_only()
    async def set_attribute(self, interaction: discord.Interaction, user: discord.User, attribute: Literal["faylen", "virelite", "fayrites", "fayrite_shards", "ethryl", "remna", "xp", "loot_chests", "level", "level_cap"], amount: int):
        await self._adjust(interaction, user, attribute, "set", amount)

    @reset_group.command(name="daily", description="Reset a user's /daily claim and summon cooldowns.")
    @owner_only()
    async def reset_daily(self, interaction: discord.Interaction, user: discord.User):
        async with get_session() as s:
            u = await s.get(User, str(user.id), with_for_update=True)
            if not u: return await interaction.followup.send("❌ User not registered.", ephemeral=True)
            u.last_daily_claim = None
            u.last_daily_summon = None
            await s.commit()
        await interaction.followup.send(f"✅ Daily timers reset for {user.mention}.", ephemeral=True)

    @reload_group.command(name="config", description="Reload all config files and apply changes by reloading cogs.")
    @owner_only()
    async def reload_config(self, interaction: discord.Interaction):
        if not hasattr(self.bot, 'config_manager') or not hasattr(self.bot.config_manager, 'load_all'):
            return await interaction.followup.send(
                "❌ **Critical Error:** `bot.config_manager` is not implemented correctly. Configs cannot be reloaded.",
                ephemeral=True
            )
        try:
            self.bot.config_manager.load_all()
            self.bot.config = self.bot.config_manager.configs
            logger.info(f"CONFIG RELOAD triggered by {interaction.user}")
            reloaded_cogs, failed_cogs = [], []
            initial_cogs = getattr(self.bot, 'initial_cogs', [])
            for cog in initial_cogs:
                try:
                    await self.bot.reload_extension(cog)
                    reloaded_cogs.append(f"`{cog}`")
                except Exception:
                    failed_cogs.append(f"`{cog}`")
            await interaction.followup.send(
                "✅ Configs reloaded from disk.\n"
                f"✅ Cogs reloaded to apply changes: {', '.join(reloaded_cogs)}\n"
                + (f"❌ Failed to reload: {', '.join(failed_cogs)}" if failed_cogs else ""),
                ephemeral=True
            )
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
            await interaction.followup.send(f"❌ Error reloading `{cog_name}`:\n```py\n{traceback.format_exc(limit=1)}\n```", ephemeral=True)

    @reload_group.command(name="esprits", description="Reload Esprit static data from JSON into the database.")
    @owner_only()
    async def reload_esprits(self, interaction: discord.Interaction, force_update: bool = False):
        await interaction.followup.send("⏳ Reloading Esprit data...", ephemeral=True)
        try:
            loader = EspritDataLoader()
            count = await loader.load_esprits(force_reload=force_update)
            missing = await loader.verify_data_integrity()
            message = f"✅ Loaded/Updated **{count:,}** esprit entries."
            if missing: message += f"\n⚠️ **{len(missing)}** Esprits from JSON are still missing from the database."
            await interaction.edit_original_response(content=message)
        except FileNotFoundError:
            await interaction.edit_original_response(content="❌ `esprits.json` not found in the expected directory.")
        except Exception as exc:
            logger.error("Failed to reload Esprit data", exc_info=True)
            await interaction.edit_original_response(content=f"❌ An unexpected error occurred: `{exc}`")

async def setup(bot: commands.Bot):
    # This single line correctly loads the cog and registers all its commands.
    await bot.add_cog(AdminCog(bot))
    logger.info("✅ AdminCog loaded")
