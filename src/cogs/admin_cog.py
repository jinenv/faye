#  src/cogs/admin_cog.py
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

# ──────────────────────────────── help UI ────────────────────────────────────
class AdminHelpSelect(discord.ui.Select):
    """Dropdown for selecting an admin-command category."""
    def __init__(self, command_data: Dict[str, dict]):
        self.command_data = command_data
        options = [
            discord.SelectOption(
                label=d["name"], value=k, emoji=d["emoji"], description=d["description"][:95]
            ) for k, d in command_data.items()
        ]
        super().__init__(placeholder="Pick a category…", options=options)

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        data = self.command_data[key]
        embed = discord.Embed(
            title=f"{data['emoji']} {data['name']}",
            description=data["description"],
            color=discord.Color.orange(),
        )
        for cmd in data["commands"]:
            embed.add_field(name=f"`{cmd['name']}`", value=f"Usage: `{cmd['usage']}`\n{cmd['desc']}", inline=False)
        await interaction.response.edit_message(embed=embed, view=self.view)

class AdminHelpView(discord.ui.View):
    def __init__(self, author_id: int, command_data: Dict[str, dict]):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.add_item(AdminHelpSelect(command_data))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This menu isn’t for you.", ephemeral=True)
            return False
        return True

# ─────────────────────────────── stats UI ────────────────────────────────────
class StatsView(discord.ui.View):
    def __init__(self, stats: dict, author_id: int, refresh_cb):
        super().__init__(timeout=300)
        self.stats = stats
        self.author_id = author_id
        self.refresh_cb = refresh_cb
        self.page = "overview"

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.author_id:
            await i.response.send_message("❌ This menu isn’t for you.", ephemeral=True)
            return False
        return True

    # ── embeds ─────────────────────────────────────────────────────────────
    def _build_overview(self):
        s = self.stats
        return (
            discord.Embed(
                title="📊 Global Overview",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow(),
                description="Key metrics for the whole cluster",
            )
            .add_field(
                name="Users / Servers",
                value=f"Users **{s['total_users']:,}**\nGuilds **{s['guild_count']:,}**",
                inline=True,
            )
            .add_field(
                name="Esprits",
                value=f"Owned **{s['total_esprits_owned']:,}**\nUnique **{s['unique_esprits_owned']}/{s['total_esprit_types']}**",
                inline=True,
            )
            .add_field(
                name="Economy",
                value=f"Faylen **{s['total_faylen']:,}**\nEthryl **{s['total_ethryl']:,}**",
                inline=True,
            )
            .set_footer(text=f"Uptime: {s['uptime']}")
        )

    def _build_economy(self):
        s = self.stats
        return (
            discord.Embed(
                title="💰 Economy Totals",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(
                name="Currencies",
                value=(
                    f"Faylen **{s['total_faylen']:,}**\n"
                    f"Virelite **{s['total_virelite']:,}**\n"
                    f"Fayrites **{s['total_fayrites']:,}**\n"
                    f"Shards **{s['total_fayrite_shards']:,}**"
                ),
                inline=False,
            )
        )

    def _build_esprits(self):
        s = self.stats
        return (
            discord.Embed(
                title="🔮 Esprit Stats",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(
                name="Collected",
                value=f"Total **{s['total_esprits_owned']:,}**\nUnique **{s['unique_esprits_owned']}**",
                inline=True,
            )
        )

    def _build_users(self):
        s = self.stats
        return (
            discord.Embed(
                title="👥 User Engagement",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(
                name="Active",
                value=f"Today **{s['users_claimed_today']:,}**\n7-day **{s['active_users']:,}**",
                inline=True,
            )
        )

    def _embed(self):
        return {
            "overview": self._build_overview,
            "economy": self._build_economy,
            "esprits": self._build_esprits,
            "users": self._build_users,
        }[self.page]()

    # ── buttons ────────────────────────────────────────────────────────────
    @discord.ui.button(label="Overview", style=discord.ButtonStyle.primary, emoji="📊")
    async def ov_btn(self, i: discord.Interaction, _):
        self.page = "overview"
        await i.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Economy", style=discord.ButtonStyle.success, emoji="💰")
    async def eco_btn(self, i: discord.Interaction, _):
        self.page = "economy"
        await i.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Esprits", style=discord.ButtonStyle.secondary, emoji="🔮")
    async def esp_btn(self, i: discord.Interaction, _):
        self.page = "esprits"
        await i.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Users", style=discord.ButtonStyle.secondary, emoji="👥")
    async def usr_btn(self, i: discord.Interaction, _):
        self.page = "users"
        await i.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def ref_btn(self, i: discord.Interaction, _):
        self.stats = await self.refresh_cb()
        await i.response.edit_message(embed=self._embed(), view=self)


# ────────────────────────────── paginator UI ────────────────────────────────
class EspritPaginatorView(discord.ui.View):
    def __init__(self, author: int, display_name: str, data: List[Tuple[UserEsprit, EspritData]]):
        super().__init__(timeout=180)
        self.author = author
        self.data = data
        self.per_page = 5
        self.page = 0
        self.name = display_name
        self.max_page = (len(data) - 1) // self.per_page

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.author:
            await i.response.send_message("❌ Not your paginator.", ephemeral=True)
            return False
        return True

    def _embed(self):
        start = self.page * self.per_page
        end = start + self.per_page
        embed = discord.Embed(
            title=f"🔮 {self.name}'s Esprits", color=discord.Color.purple()
        )
        for ue, ed in self.data[start:end]:
            embed.add_field(
                name=f"{ed.name} (ID `{ue.id}`)",
                value=f"Lvl {ue.current_level} • {ed.rarity}",
                inline=False,
            )
        embed.set_footer(text=f"Page {self.page+1}/{self.max_page+1}")
        return embed

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, i: discord.Interaction, _):
        self.page = max(0, self.page - 1)
        await i.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def nxt(self, i: discord.Interaction, _):
        self.page = min(self.max_page, self.page + 1)
        await i.response.edit_message(embed=self._embed(), view=self)


# ────────────────────────────── main admin cog ──────────────────────────────
@app_commands.guild_only()
class AdminCog(commands.Cog):
    admin_group  = app_commands.Group(name="admin",  description="Core admin commands.")
    give_group   = app_commands.Group(name="give",   description="Give currency/items.")
    remove_group = app_commands.Group(name="remove", description="Remove currency/items.")
    set_group    = app_commands.Group(name="set",    description="Set exact values.")
    reset_group  = app_commands.Group(name="reset",  description="Reset data/cooldowns.")
    list_group   = app_commands.Group(name="list",   description="List data.")
    reload_group = app_commands.Group(name="reload", description="Reload subsystems.")

    MODIFIABLE_ATTRIBUTES = (
        "faylen", "virelite", "fayrites", "fayrite_shards",
        "ethryl", "remna", "xp", "loot_chests",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache = CacheManager(default_ttl=300)
        self.help_meta: Dict[str, dict] = {
            "give": {"name": "🎁 Give", "emoji": "🎁", "description": "Add currency/items.", "commands": []},
            "remove": {"name": "➖ Remove", "emoji": "➖", "description": "Subtract currency/items.", "commands": []},
            "set": {"name": "⚙️ Set", "emoji": "⚙️", "description": "Set an exact value.", "commands": []},
            "utility": {"name": "🛠️ Utility", "emoji": "🛠️", "description": "Stats, inspect, reload…", "commands": []},
        }

    # ── stats gatherer (cached) ────────────────────────────────────────────
    async def _gather_stats(self):
        async with get_session() as s:
            data = {
                "total_users":            (await s.scalar(select(func.count(User.user_id)))) or 0,
                "total_faylen":           (await s.scalar(select(func.sum(User.faylen)))) or 0,
                "total_virelite":         (await s.scalar(select(func.sum(User.virelite)))) or 0,
                "total_fayrites":         (await s.scalar(select(func.sum(User.fayrites)))) or 0,
                "total_ethryl":           (await s.scalar(select(func.sum(User.ethryl)))) or 0,
                "total_fayrite_shards":   (await s.scalar(select(func.sum(User.fayrite_shards)))) or 0,
                "total_esprits_owned":    (await s.scalar(select(func.count(UserEsprit.id)))) or 0,
                "unique_esprits_owned":   (await s.scalar(select(func.count(func.distinct(UserEsprit.esprit_data_id))))) or 0,
                "total_esprit_types":     (await s.scalar(select(func.count(EspritData.esprit_id)))) or 1,
            }
            today = datetime.utcnow().date()
            week  = datetime.utcnow() - timedelta(days=7)
            data["users_claimed_today"] = await s.scalar(
                select(func.count(User.user_id)).where(
                    User.last_daily_claim.is_not(None),
                    func.date(User.last_daily_claim) == today,
                )
            ) or 0
            data["active_users"] = await s.scalar(
                select(func.count(User.user_id)).where(User.last_daily_claim >= week)
            ) or 0

        data["guild_count"]  = len(self.bot.guilds)
        data["member_count"] = sum(g.member_count or 0 for g in self.bot.guilds)
        data["uptime"]       = discord.utils.format_dt(getattr(self.bot, "start_time", discord.utils.utcnow()), "R")
        return data

    # ─╢ shared attribute mutator ╟──────────────────────────────────────────
    async def _adjust(self, interaction: discord.Interaction, user: discord.User, attr: str, op: str, amount: int):
        """Shared logic for modifying a user's currency/attribute."""
        if attr not in self.MODIFIABLE_ATTRIBUTES:
            return await interaction.followup.send("❌ Invalid attribute.")
        
        async with get_session() as s:
            u = await s.get(User, str(user.id))
            if not u:
                return await interaction.followup.send("❌ Target user has no data.")
            
            old_val = getattr(u, attr)
            if op == "give": new_val = old_val + amount
            elif op == "remove": new_val = max(0, old_val - amount)
            else: new_val = amount
            setattr(u, attr, new_val)
            await s.commit()
            
        verb = op.title()
        await interaction.followup.send(f"✅ {verb} {attr.replace('_',' ').title()}: **{old_val:,} → {new_val:,}** for {user.mention}")

    async def _currency_cmd(self, interaction: discord.Interaction, user: discord.User, amount: int, attr: str, op: str):
        if amount < 0 and op != "set":
            return await interaction.followup.send("❌ Amount must be positive.")
        await self._adjust(interaction, user, attr, op, amount)

    # ───────────────────────── HELP / STATS / INSPECT ──────────────────────
    @admin_group.command(name="help", description="Interactive admin manual")
    @owner_only()
    async def admin_help(self, interaction: discord.Interaction):
        await interaction.followup.send(
            embed=discord.Embed(
                title="🛠️ Admin Command Center",
                description="Select a category from the dropdown below.",
                color=discord.Color.orange(),
            ),
            view=AdminHelpView(interaction.user.id, self.help_meta),
        )

    @admin_group.command(name="stats", description="Global bot statistics")
    @owner_only(ephemeral=False)
    async def admin_stats(self, interaction: discord.Interaction):
        key = "admin:stats"
        stats = await self.cache.get(key)
        if stats is None:
            stats = await self._gather_stats()
            await self.cache.set(key, stats)
        await interaction.followup.send(
            embed=StatsView(stats, interaction.user.id, self._gather_stats)._embed(),
            view=StatsView(stats, interaction.user.id, self._gather_stats),
        )

    @admin_group.command(name="inspect", description="Inspect a user’s record")
    @owner_only()
    async def inspect(self, interaction: discord.Interaction, user: discord.User):
        async with get_session() as s:
            u = await s.get(User, str(user.id))
            if not u:
                return await interaction.followup.send("❌ User not registered.")
            esprit_count = await s.scalar(
                select(func.count(UserEsprit.id)).where(UserEsprit.owner_id == str(user.id))
            ) or 0
        embed = (
            discord.Embed(title=f"🔍 Inspect: {user.display_name}", color=discord.Color.gold())
            .add_field(name="Level / XP", value=f"{u.level} / {u.xp:,}", inline=True)
            .add_field(name="Esprits", value=f"{esprit_count:,}", inline=True)
            .add_field(name="Faylen", value=f"{u.faylen:,}", inline=True)
            .add_field(name="Virelite", value=f"{u.virelite:,}", inline=True)
            .set_footer(text=f"User ID: {u.user_id}")
        )
        await interaction.followup.send(embed=embed)

    # ───────────────────────────── GIVE commands ───────────────────────────
    @give_group.command(name="faylen", description="Give Faylen to a user.")
    @owner_only()
    async def give_faylen(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "faylen", "give", amount)
    
    @give_group.command(name="virelite", description="Give Virelite to a user.")
    @owner_only()
    async def give_virelite(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "virelite", "give", amount)

    @give_group.command(name="fayrites", description="Give Fayrites to a user.")
    @owner_only()
    async def give_fayrites(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "fayrites", "give", amount)

    @give_group.command(name="fayrite-shards", description="Give Fayrite Shards to a user.")
    @owner_only()
    async def give_fayrite_shards(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "fayrite_shards", "give", amount)

    @give_group.command(name="ethryl", description="Give Ethryl to a user.")
    @owner_only()
    async def give_ethryl(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "ethryl", "give", amount)

    @give_group.command(name="remna", description="Give Remna to a user.")
    @owner_only()
    async def give_remna(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "remna", "give", amount)

    @give_group.command(name="xp", description="Give XP to a user.")
    @owner_only()
    async def give_xp(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "xp", "give", amount)

    @give_group.command(name="loot-chests", description="Give Loot Chests to a user.")
    @owner_only()
    async def give_loot_chests(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "loot_chests", "give", amount)

    # ───────────────────────────── REMOVEcommands ──────────────────────────
    @remove_group.command(name="faylen", description="Remove Faylen from a user.")
    @owner_only()
    async def remove_faylen(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "faylen", "remove", amount)

    @remove_group.command(name="virelite", description="Remove Virelite from a user.")
    @owner_only()
    async def remove_virelite(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "virelite", "remove", amount)

    @remove_group.command(name="fayrites", description="Remove Fayrites from a user.")
    @owner_only()
    async def remove_fayrites(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "fayrites", "remove", amount)

    @remove_group.command(name="fayrite-shards", description="Remove Fayrite Shards from a user.")
    @owner_only()
    async def remove_fayrite_shards(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "fayrite_shards", "remove", amount)

    @remove_group.command(name="ethryl", description="Remove Ethryl from a user.")
    @owner_only()
    async def remove_ethryl(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "ethryl", "remove", amount)

    @remove_group.command(name="remna", description="Remove Remna from a user.")
    @owner_only()
    async def remove_remna(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "remna", "remove", amount)

    @remove_group.command(name="xp", description="Remove XP from a user.")
    @owner_only()
    async def remove_xp(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "xp", "remove", amount)

    @remove_group.command(name="loot-chests", description="Remove Loot Chests from a user.")
    @owner_only()
    async def remove_loot_chests(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "loot_chests", "remove", amount)

    # ───────────────────────────── SET commands ──────────────────────────
    @set_group.command(name="faylen", description="Set Faylen for a user.")
    @owner_only()
    async def set_faylen(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "faylen", "set", amount)

    @set_group.command(name="virelite", description="Set Virelite for a user.")
    @owner_only()
    async def set_virelite(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "virelite", "set", amount)

    @set_group.command(name="fayrites", description="Set Fayrites for a user.")
    @owner_only()
    async def set_fayrites(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "fayrites", "set", amount)

    @set_group.command(name="fayrite-shards", description="Set Fayrite Shards for a user.")
    @owner_only()
    async def set_fayrite_shards(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "fayrite_shards", "set", amount)

    @set_group.command(name="ethryl", description="Set Ethryl for a user.")
    @owner_only()
    async def set_ethryl(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "ethryl", "set", amount)

    @set_group.command(name="remna", description="Set Remna for a user.")
    @owner_only()
    async def set_remna(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "remna", "set", amount)

    @set_group.command(name="xp", description="Set XP for a user.")
    @owner_only()
    async def set_xp(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "xp", "set", amount)

    @set_group.command(name="loot-chests", description="Set Loot Chests for a user.")
    @owner_only()
    async def set_loot_chests(self, interaction: discord.Interaction, user: discord.User, amount: int): await self._adjust(interaction, user, "loot_chests", "set", amount)
    
    # ───────────────────────────── RESET commands ──────────────────────────
    @reset_group.command(name="daily", description="Reset a user's /daily cooldown")
    @owner_only()
    async def reset_daily(self, interaction: discord.Interaction, user: discord.User):
        async with get_session() as s:
            u = await s.get(User, str(user.id))
            if not u:
                return await interaction.followup.send("❌ User not registered.")
            u.last_daily_claim = None
            await s.commit()
        await interaction.followup.send("✅ Daily timer reset.")

    # ───────────────────────────── LIST commands ───────────────────────────
    @list_group.command(name="users", description="Top 25 users by level")
    @owner_only()
    async def list_users(self, interaction: discord.Interaction):
        async with get_session() as s:
            rows = (
                await s.execute(
                    select(User).order_by(User.level.desc(), User.xp.desc()).limit(25)
                )
            ).scalars().all()
        if not rows:
            return await interaction.followup.send("No users.")
        embed = discord.Embed(title="🏆 Top Users", color=discord.Color.green())
        for idx, u in enumerate(rows, 1):
            name = self.bot.get_user(int(u.user_id)) or f"ID {u.user_id}"
            embed.add_field(name=f"{idx}. {name}", value=f"Lvl {u.level} • XP {u.xp:,}", inline=False)
        await interaction.followup.send(embed=embed)

    @list_group.command(name="esprits", description="List a user's esprits")
    @owner_only()
    async def list_esprits(self, interaction: discord.Interaction, user: discord.User):
        async with get_session() as s:
            rows = (
                await s.execute(
                    select(UserEsprit, EspritData)
                    .join(EspritData, UserEsprit.esprit_data_id == EspritData.esprit_id)
                    .where(UserEsprit.owner_id == str(user.id))
                    .options(selectinload(UserEsprit.esprit_data))
                    .order_by(EspritData.rarity.desc(), UserEsprit.current_level.desc())
                )
            ).all()
        if not rows:
            return await interaction.followup.send("No esprits.")
        view = EspritPaginatorView(interaction.user.id, user.display_name, rows)
        await interaction.followup.send(embed=view._embed(), view=view)

    # ───────────────────────────── RELOAD commands ─────────────────────────
    @reload_group.command(name="config", description="Reload all config files")
    @owner_only()
    async def reload_config(self, interaction: discord.Interaction):
        try:
            self.bot.config_manager.reload()
            await interaction.followup.send("✅ Configuration reloaded.")
        except Exception as exc:
            logger.error("Config reload failed", exc_info=True)
            await interaction.followup.send(f"❌ Failed: {exc}")

    @reload_group.command(name="cog", description="Reload a single cog")
    @app_commands.autocomplete(cog_name=cog_autocomplete)
    @owner_only()
    async def reload_cog(self, interaction: discord.Interaction, cog_name: str):
        try:
            await self.bot.reload_extension(cog_name)
            await interaction.followup.send(f"✅ Reloaded `{cog_name}`.")
        except Exception:
            await interaction.followup.send(
                f"❌ Error reloading `{cog_name}`:\n```py\n{traceback.format_exc()[:1900]}```"
            )

    @reload_group.command(name="esprits", description="Reload esprit data from JSON")
    @owner_only()
    async def reload_esprits(self, interaction: discord.Interaction, force: bool = False):
        try:
            loader = EspritDataLoader()
            count = await loader.load_esprits(force_reload=force)
            await loader.verify_data_integrity()
            await interaction.followup.send(f"✅ Loaded **{count:,}** esprit entries.")
        except FileNotFoundError:
            await interaction.followup.send("❌ esprits.json not found.")
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed: {exc}")

# ───────────────────────────── cog setup ────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
    logger.info("✅ AdminCog loaded")
