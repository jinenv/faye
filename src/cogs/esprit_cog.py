# src/cogs/esprit_cog.py
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Union, Set

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger
from src.utils.progression_manager import ProgressionManager
from src.utils.cache_manager import CacheManager
from src.utils.rate_limiter import RateLimiter
from enum import Enum

logger = get_logger(__name__)

class TeamSlot(Enum):
    leader   = 1
    support1 = 2
    support2 = 3
    
# ---------------------------------------------------------------- Constants
MAX_COLLECTION_PAGE_SIZE = 25
INTERACTION_TIMEOUT = 180
CACHE_TTL = 300
MAX_BULK_OPERATIONS = 10

# ────────────────────────────────────────────────────────────────────────────
# UI Components
# ────────────────────────────────────────────────────────────────────────────
class ConfirmationView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.result: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This confirmation isn’t for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def _confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.result = True
        self.stop()
        await interaction.response.edit_message(content="✅ Confirmed", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def _cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.result = False
        self.stop()
        await interaction.response.edit_message(content="❌ Cancelled", view=None)


class EnhancedCollectionView(discord.ui.View):
    """Paginated, sortable, filterable Esprit collection."""

    def __init__(
        self,
        all_esprits: List[UserEsprit],
        author_id: int,
        bot: commands.Bot,
    ):
        super().__init__(timeout=INTERACTION_TIMEOUT)
        self.all_esprits = all_esprits
        self.filtered_esprits = all_esprits
        self.author_id = author_id
        self.bot = bot
        self.current_page = 0
        self.sort_by = "name"  # name | level | rarity
        self.filter_rarity: Optional[str] = None
        self.page_size = 10

        self.update_pages()
        self.update_buttons()

    # ── helpers ────────────────────────────────────────────────────────────
    def _rarity_order(self, r: str) -> int:
        return {
            "Common": 0,
            "Uncommon": 1,
            "Rare": 2,
            "Epic": 3,
            "Celestial": 4,
            "Supreme": 5,
            "Deity": 6,
        }.get(r, 0)

    def _rarity_emoji(self, r: str) -> str:
        return {
            "Common": "⚪",
            "Uncommon": "🟢",
            "Rare": "🔵",
            "Epic": "🟣",
            "Celestial": "🟡",
            "Supreme": "🔴",
            "Deity": "🌟",
        }.get(r, "❓")

    # ── pagination ─────────────────────────────────────────────────────────
    def update_pages(self) -> None:
        # filter
        self.filtered_esprits = (
            [e for e in self.all_esprits if e.esprit_data.rarity == self.filter_rarity]
            if self.filter_rarity
            else list(self.all_esprits)
        )

        # sort
        if self.sort_by == "name":
            self.filtered_esprits.sort(key=lambda e: e.esprit_data.name)
        elif self.sort_by == "level":
            self.filtered_esprits.sort(key=lambda e: e.current_level, reverse=True)
        elif self.sort_by == "rarity":
            self.filtered_esprits.sort(
                key=lambda e: self._rarity_order(e.esprit_data.rarity), reverse=True
            )

        self.pages = self._build_embeds()
        self.current_page = min(self.current_page, len(self.pages) - 1)

    def _build_embeds(self) -> List[discord.Embed]:
        if not self.filtered_esprits:
            return [
                discord.Embed(
                    title="📦 Esprit Collection",
                    description="No Esprits match these filters.",
                    color=discord.Color.light_grey(),
                )
            ]

        total_sigil = sum(e.calculate_power() for e in self.filtered_esprits)
        pages: List[discord.Embed] = []

        for i in range(0, len(self.filtered_esprits), self.page_size):
            chunk = self.filtered_esprits[i : i + self.page_size]
            embed = discord.Embed(
                title="📦 Esprit Collection",
                description=(
                    f"**Total:** {len(self.filtered_esprits)}"
                    f" | **Sigil:** {total_sigil:,}"
                    f" | **Page:** {i//self.page_size + 1}/"
                    f"{(len(self.filtered_esprits)-1)//self.page_size + 1}"
                ),
                color=discord.Color.dark_gold(),
            )

            for ue in chunk:
                rarity_emoji = self._rarity_emoji(ue.esprit_data.rarity)
                team_indicator = ""
                if hasattr(self, "user_data"):
                    if ue.id == self.user_data.get("active_esprit_id"):
                        team_indicator = " 👑"
                    elif ue.id in {
                        self.user_data.get("support1_esprit_id"),
                        self.user_data.get("support2_esprit_id"),
                    }:
                        team_indicator = " ⚔️"

                embed.add_field(
                    name=f"{rarity_emoji} **{ue.esprit_data.name}**{team_indicator}",
                    value=(
                        f"ID: `{ue.id}`"
                        f" | Lvl: **{ue.current_level}**"
                        f" | Sigil: **{ue.calculate_power():,}**"
                    ),
                    inline=False,
                )

            embed.set_footer(
                text=f"Sort: {self.sort_by.title()} • "
                f"Filter: {self.filter_rarity or 'All'}"
            )
            pages.append(embed)

        return pages

    # ── discord.ui plumbing ────────────────────────────────────────────────
    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message(
                "You can’t control this view.", ephemeral=True
            )
            return False
        return True

    def update_buttons(self) -> None:
        self.first_button.disabled = self.current_page == 0
        self.previous_button.disabled = self.current_page == 0
        self.last_button.disabled = self.current_page >= len(self.pages) - 1
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    # ── nav buttons ────────────────────────────────────────────────────────
    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_button(self, inter: discord.Interaction, _: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await inter.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_button(self, inter: discord.Interaction, _: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await inter.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, inter: discord.Interaction, _: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await inter.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_button(self, inter: discord.Interaction, _: discord.ui.Button):
        self.current_page = len(self.pages) - 1
        self.update_buttons()
        await inter.response.edit_message(embed=self.pages[self.current_page], view=self)

    # ── sort / filter selects ──────────────────────────────────────────────
    @discord.ui.select(
        placeholder="Sort by…",
        options=[
            discord.SelectOption(label="Name", value="name", emoji="📝"),
            discord.SelectOption(label="Level", value="level", emoji="📈"),
            discord.SelectOption(label="Rarity", value="rarity", emoji="💎"),
        ],
    )
    async def sort_select(self, inter: discord.Interaction, select: discord.ui.Select):
        self.sort_by = select.values[0]
        self.update_pages()
        self.update_buttons()
        await inter.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.select(
        placeholder="Filter by rarity…",
        options=[
            discord.SelectOption(label="All", value="all", emoji="🌟"),
            discord.SelectOption(label="Common", value="Common", emoji="⚪"),
            discord.SelectOption(label="Uncommon", value="Uncommon", emoji="🟢"),
            discord.SelectOption(label="Rare", value="Rare", emoji="🔵"),
            discord.SelectOption(label="Epic", value="Epic", emoji="🟣"),
            discord.SelectOption(label="Celestial", value="Celestial", emoji="🟡"),
            discord.SelectOption(label="Supreme", value="Supreme", emoji="🔴"),
            discord.SelectOption(label="Deity", value="Deity", emoji="🌟"),
        ],
    )
    async def filter_select(self, inter: discord.Interaction, select: discord.ui.Select):
        self.filter_rarity = None if select.values[0] == "all" else select.values[0]
        self.current_page = 0
        self.update_pages()
        self.update_buttons()
        await inter.response.edit_message(embed=self.pages[self.current_page], view=self)


class BulkDissolveView(discord.ui.View):
    """Interactive multi-dissolve selection."""

    def __init__(self, esprits: List[UserEsprit], author_id: int):
        super().__init__(timeout=300)
        self.esprits = esprits[:MAX_BULK_OPERATIONS]
        self.author_id = author_id
        self.selected_ids: Set[str] = set()
        self._refresh_options()

    # ── helpers ────────────────────────────────────────────────────────────
    def _rarity_emoji(self, r: str) -> str:
        return {
            "Common": "⚪",
            "Uncommon": "🟢",
            "Rare": "🔵",
            "Epic": "🟣",
            "Celestial": "🟡",
            "Supreme": "🔴",
            "Deity": "🌟",
        }.get(r, "❓")

    def _refresh_options(self) -> None:
        opts: List[discord.SelectOption] = []
        for e in self.esprits:  # ≤25 by ctor
            emoji = self._rarity_emoji(e.esprit_data.rarity)
            opts.append(
                discord.SelectOption(
                    label=f"{e.esprit_data.name} • Lvl {e.current_level}",
                    value=e.id,
                    emoji=emoji,
                    description=f"{e.esprit_data.rarity} | ID:{e.id[:8]}",
                )
            )
        self.select_menu.options = opts
        self.dissolve_button.disabled = not self.selected_ids

    # ── ui elements ────────────────────────────────────────────────────────
    @discord.ui.select(
        placeholder="Select Esprits to dissolve…",
        min_values=0,
        max_values=25,
    )
    async def select_menu(self, inter: discord.Interaction, select: discord.ui.Select):
        self.selected_ids = set(select.values)
        self.dissolve_button.disabled = not self.selected_ids
        await inter.response.edit_message(view=self)

    @discord.ui.button(
        label="Dissolve Selected", style=discord.ButtonStyle.danger, disabled=True
    )
    async def dissolve_button(self, inter: discord.Interaction, _: discord.ui.Button):
        if not self.selected_ids:
            return
        confirm = ConfirmationView(self.author_id)
        await inter.response.send_message(
            embed=discord.Embed(
                title="⚠️ Confirm Bulk Dissolve",
                description=f"Dissolve **{len(self.selected_ids)}** Esprit(s)?",
                color=discord.Color.red(),
            ),
            view=confirm,
            ephemeral=True,
        )
        await confirm.wait()
        if confirm.result:
            self.stop()

    # ── perms ──────────────────────────────────────────────────────────────
    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Not your session.", ephemeral=True)
            return False
        return True


# ────────────────────────────────────────────────────────────────────────────
# Slash-Command Group
# ────────────────────────────────────────────────────────────────────────────
@app_commands.guild_only()
class EspritGroup(app_commands.Group, name="esprit"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.cache = CacheManager(default_ttl=CACHE_TTL)
        self.rate_limiter = RateLimiter(calls=5, period=60)

        # nested group for team
        self.team = app_commands.Group(
            name="team", description="Manage your combat team", parent=self
        )
        self.team.add_command(
           app_commands.Command(
                name="view",
                callback=self.team_view,
                description="View your current leader / supports."
            )
        )
        self.team.add_command(
            app_commands.Command(
                name="set",
                callback=self.team_set,
                description="Assign an Esprit to a team slot.",
            )
        )
        self.team.add_command(
            app_commands.Command(
                name="optimize",
                callback=self.team_optimize,
                description="AI-driven recommendation.",
            )
        )

    # ── misc helpers ───────────────────────────────────────────────────────
    async def _ensure_user(self, user_id: str) -> None:
        async with get_session() as s:
            if not await s.get(User, user_id):
                s.add(User(user_id=user_id, username="Unknown"))
                await s.commit()

    async def _get_collection(self, user_id: str) -> List[UserEsprit]:
        cache_key = f"user:{user_id}:collection"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async with get_session() as s:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.owner_id == user_id)
                .options(selectinload(UserEsprit.esprit_data))
            )
            result = (await s.execute(stmt)).scalars().all()
            await self.cache.set(cache_key, result)
            return result

    async def _invalidate(self, user_id: str) -> None:
        await self.cache.clear_pattern(f"user:{user_id}:")

    # ────────────────────────────────────────────────────────────────────
    # collection
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="collection", description="Show your Esprits.")
    async def collection(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        await self._ensure_user(str(inter.user.id))
        esprits = await self._get_collection(str(inter.user.id))

        if not esprits:
            return await inter.followup.send(
                embed=discord.Embed(
                    title="🌱 No Esprits Yet",
                    description="Use `/summon` to obtain your first Esprit.",
                    color=discord.Color.blue(),
                )
            )

        async with get_session() as s:
            u = await s.get(User, str(inter.user.id))
            user_data = {
                "active_esprit_id": u.active_esprit_id,
                "support1_esprit_id": u.support1_esprit_id,
                "support2_esprit_id": u.support2_esprit_id,
            }

        view = EnhancedCollectionView(esprits, inter.user.id, self.bot)
        view.user_data = user_data
        await inter.followup.send(embed=view.pages[0], view=view)

    # ────────────────────────────────────────────────────────────────────
    # details
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="details", description="Full stat sheet.")
    @app_commands.describe(esprit_id="Copy ID from /esprit collection.")
    async def details(self, inter: discord.Interaction, esprit_id: str):
        await inter.response.defer(ephemeral=True)

        async with get_session() as s:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id == esprit_id)
                .options(selectinload(UserEsprit.esprit_data))
            )
            ue = (await s.execute(stmt)).scalar_one_or_none()

            if not ue or ue.owner_id != str(inter.user.id):
                return await inter.followup.send("❌ Not found / not yours.", ephemeral=True)

            ed = ue.esprit_data

            lvl_mult = 1 + (ue.current_level - 1) * 0.05
            stat = lambda base: int(base * lvl_mult)

            embed = discord.Embed(
                title=f"{ed.name} • Lvl {ue.current_level}",
                color=self._rarity_color(ed.rarity),
            )

            embed.add_field(
                name="Identity",
                value=f"ID `{ue.id}`\n{ed.rarity} {self._rarity_emoji(ed.rarity)}",
                inline=True,
            )

            embed.add_field(
                name="Primary Stats",
                value=(
                    f"HP **{stat(ed.base_hp):,}**\n"
                    f"ATK **{stat(ed.base_attack)}**\n"
                    f"DEF **{stat(ed.base_defense)}**\n"
                    f"SPD **{stat(ed.base_speed)}**"
                ),
                inline=True,
            )

            embed.add_field(
                name="Secondary Stats",
                value=(
                    f"MagicRes **{stat(ed.base_magic_resist)}**\n"
                    f"Crit {ed.base_crit_rate:.0%}\n"
                    f"Block {ed.base_block_rate:.0%}\n"
                    f"Dodge {ed.base_dodge_chance:.0%}"
                ),
                inline=True,
            )

            embed.add_field(
                name="Mana",
                value=(
                    f"Max **{ed.base_mana}**\n"
                    f"Regen **{ed.base_mana_regen}** / t"
                ),
                inline=True,
            )

            embed.add_field(
                name="Sigil",
                value=f"{ue.calculate_power():,}",
                inline=True,
            )

            if ed.description:
                embed.add_field(
                    name="Lore",
                    value=(ed.description[:200] + "…")
                    if len(ed.description) > 200
                    else ed.description,
                    inline=False,
                )

            if getattr(ed, "image_url", None):
                embed.set_thumbnail(url=ed.image_url)

            await inter.followup.send(embed=embed)

    # ────────────────────────────────────────────────────────────────────
    # upgrade
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="upgrade", description="Spend Moonglow for levels.")
    @app_commands.describe(
        esprit_id="Target Esprit ID",
        levels="Levels to add (1-10).",
    )
    async def upgrade(
        self,
        inter: discord.Interaction,
        esprit_id: str,
        levels: int = 1,
    ):
        if not (1 <= levels <= 10):
            return await inter.response.send_message("Levels must be 1-10.", ephemeral=True)
        await inter.response.defer(ephemeral=True)

        if not await self.rate_limiter.check(str(inter.user.id)):
            wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
            return await inter.followup.send(f"Cooldown {wait}s.", ephemeral=True)

        async with get_session() as s:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id == esprit_id)
                .options(selectinload(UserEsprit.esprit_data))
                .with_for_update()
            )
            ue = (await s.execute(stmt)).scalar_one_or_none()
            if not ue or ue.owner_id != str(inter.user.id):
                return await inter.followup.send("❌ Not found / not yours.", ephemeral=True)

            user = await s.get(User, str(inter.user.id), with_for_update=True)
            prog = ProgressionManager(self.bot.config_manager)

            max_level = prog.get_esprit_max_level_for_player(user.level)
            target_level = min(ue.current_level + levels, max_level)
            if target_level == ue.current_level:
                return await inter.followup.send(
                    f"Max level for player level {user.level} reached.", ephemeral=True
                )

            cost = sum(
                prog.get_esprit_upgrade_cost(lvl)
                for lvl in range(ue.current_level, target_level)
            )
            if user.moonglow < cost:
                return await inter.followup.send(f"Need {cost:,} Moonglow.", ephemeral=True)

            # pay & apply
            user.moonglow -= cost
            ue.current_level = target_level
            ue.current_xp = 0
            ue.current_hp = int(
                ue.esprit_data.base_hp * (1 + (target_level - 1) * 0.05)
            )

            s.add_all([user, ue])
            await s.commit()
            await self._invalidate(str(inter.user.id))

            await inter.followup.send(
                embed=discord.Embed(
                    title="⭐ Upgrade Complete",
                    description=f"{ue.esprit_data.name} → Lvl {target_level}",
                    color=discord.Color.gold(),
                )
                .add_field(name="Cost", value=f"{cost:,} Moonglow")
                .add_field(name="New HP", value=f"{ue.current_hp:,}")
                .add_field(name="Sigil", value=f"{ue.calculate_power():,}")
            )

    # ────────────────────────────────────────────────────────────────────
    # dissolve  (includes new multi flag)
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="dissolve", description="Recycle Esprit(s) for resources."
    )
    @app_commands.describe(
        esprit_id="ID to dissolve (ignored if multi=True).",
        multi="Open interactive multi-dissolve.",
        rarity_filter="Filter when using multi.",
    )
    async def dissolve(
        self,
        inter: discord.Interaction,
        esprit_id: Optional[str] = None,
        multi: bool = False,
        rarity_filter: Optional[str] = None,
    ):
        await inter.response.defer(ephemeral=True)

        if multi:
            # ── bulk dissolve ───────────────────────────────────────────────
            valid = {
                "Common",
                "Uncommon",
                "Rare",
                "Epic",
                "Celestial",
                "Supreme",
                "Deity",
            }
            if rarity_filter and rarity_filter not in valid:
                return await inter.followup.send("Invalid rarity.", ephemeral=True)

            async with get_session() as s:
                user = await s.get(User, str(inter.user.id))
                protected = {
                    user.active_esprit_id,
                    user.support1_esprit_id,
                    user.support2_esprit_id,
                }
                protected.discard(None)

                stmt = (
                    select(UserEsprit)
                    .where(
                        and_(
                            UserEsprit.owner_id == str(inter.user.id),
                            ~UserEsprit.id.in_(protected) if protected else True,
                        )
                    )
                    .options(selectinload(UserEsprit.esprit_data))
                )
                if rarity_filter:
                    stmt = stmt.where(
                        UserEsprit.esprit_data.has(rarity=rarity_filter)
                    )

                esprits = (await s.execute(stmt)).scalars().all()

            if not esprits:
                return await inter.followup.send("Nothing to dissolve.", ephemeral=True)

            view = BulkDissolveView(esprits, inter.user.id)
            await inter.followup.send(
                embed=discord.Embed(
                    title="♻️ Bulk Dissolve",
                    description="Pick up to 10 Esprits. Team members are protected.",
                    color=discord.Color.orange(),
                ),
                view=view,
            )
            await view.wait()
            if not view.selected_ids:
                return

            await self._process_bulk_dissolve(inter, view.selected_ids)
            return

        # ── single dissolve ────────────────────────────────────────────────
        if not esprit_id:
            return await inter.followup.send(
                "Provide `esprit_id` or use `multi=true`.", ephemeral=True
            )

        async with get_session() as s:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id == esprit_id)
                .options(selectinload(UserEsprit.esprit_data))
            )
            ue = (await s.execute(stmt)).scalar_one_or_none()
            if not ue or ue.owner_id != str(inter.user.id):
                return await inter.followup.send("❌ Not found / not yours.", ephemeral=True)

            user = await s.get(User, str(inter.user.id))
            if esprit_id in {
                user.active_esprit_id,
                user.support1_esprit_id,
                user.support2_esprit_id,
            }:
                return await inter.followup.send("Esprit is in your team.", ephemeral=True)

            confirm = ConfirmationView(inter.user.id)
            await inter.followup.send(
                embed=discord.Embed(
                    title="⚠️ Confirm Dissolve",
                    description=f"Dissolve **{ue.esprit_data.name}** (Lvl {ue.current_level})?",
                    color=discord.Color.orange(),
                ),
                view=confirm,
            )
            await confirm.wait()
            if not confirm.result:
                return

            rewards = self._calc_rewards([ue])
            user.moonglow += rewards["moonglow"]
            user.essence += rewards["essence"]

            await s.delete(ue)
            s.add(user)
            await s.commit()
            await self._invalidate(str(inter.user.id))

            await inter.followup.send(
                embed=discord.Embed(
                    title="♻️ Dissolved",
                    description="\n".join(f"{k.title()}: {v:,}" for k, v in rewards.items()),
                    color=discord.Color.green(),
                ),
                ephemeral=True,
            )

    # ── internal helper for bulk dissolve ──────────────────────────────────
    async def _process_bulk_dissolve(self, inter: discord.Interaction, ids: Set[str]):
        async with get_session() as s:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id.in_(ids))
                .options(selectinload(UserEsprit.esprit_data))
            )
            esprits = (await s.execute(stmt)).scalars().all()

            if len(esprits) != len(ids) or any(
                e.owner_id != str(inter.user.id) for e in esprits
            ):
                return await inter.followup.send("Ownership mismatch.", ephemeral=True)

            user = await s.get(User, str(inter.user.id), with_for_update=True)
            rewards = self._calc_rewards(esprits)
            user.moonglow += rewards["moonglow"]
            user.essence += rewards["essence"]

            for e in esprits:
                await s.delete(e)
            s.add(user)
            await s.commit()

        await self._invalidate(str(inter.user.id))
        await inter.followup.send(
            embed=discord.Embed(
                title="♻️ Bulk Dissolve Complete",
                description=(
                    f"Dissolved **{len(esprits)}** Esprit(s).\n\n"
                    + "\n".join(f"{k.title()}: {v:,}" for k, v in rewards.items())
                ),
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    # ── reward calculator ──────────────────────────────────────────────────
    def _calc_rewards(self, esprits: List[UserEsprit]) -> Dict[str, int]:
        cfg = self.bot.config_manager.get("dissolve_rewards")
        totals = {"moonglow": 0, "essence": 0}
        for e in esprits:
            r = cfg.get(e.esprit_data.rarity, {"moonglow": 0, "essence": 0})
            totals["moonglow"] += r["moonglow"]
            totals["essence"] += r["essence"]
        return totals

    # ────────────────────────────────────────────────────────────────────
    # search
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="search", description="Find Esprits by name.")
    async def search(self, inter: discord.Interaction, query: str):
        await inter.response.defer(ephemeral=True)
        esprits = await self._get_collection(str(inter.user.id))
        hits = [
            e
            for e in esprits
            if query.lower() in e.esprit_data.name.lower()
        ][:25]

        if not hits:
            return await inter.followup.send("No matches.", ephemeral=True)

        lines = [
            f"`{e.id}` • {e.esprit_data.name} • "
            f"Lvl {e.current_level} • Sigil {e.calculate_power():,}"
            for e in hits
        ]
        await inter.followup.send(
            embed=discord.Embed(
                title=f"🔍 Search ({len(hits)})", description="\n".join(lines)
            ),
            ephemeral=True,
        )

    # ────────────────────────────────────────────────────────────────────
    # compare
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="compare", description="Compare two Esprits’ Sigil and stats."
    )
    async def compare(
        self, inter: discord.Interaction, esprit_a: str, esprit_b: str
    ):
        await inter.response.defer(ephemeral=True)
        async with get_session() as s:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id.in_([esprit_a, esprit_b]))
                .options(selectinload(UserEsprit.esprit_data))
            )
            rows = (await s.execute(stmt)).scalars().all()
        if len(rows) != 2 or any(r.owner_id != str(inter.user.id) for r in rows):
            return await inter.followup.send("Bad IDs or not yours.", ephemeral=True)

        a, b = rows
        embed = discord.Embed(title="⚖️ Esprit Comparison")
        for ue in [a, b]:
            ed = ue.esprit_data
            embed.add_field(
                name=f"{ed.name} • Sigil {ue.calculate_power():,}",
                value=(
                    f"Lvl {ue.current_level} | "
                    f"{ed.rarity} {self._rarity_emoji(ed.rarity)}"
                ),
                inline=False,
            )
        await inter.followup.send(embed=embed, ephemeral=True)

    # ────────────────────────────────────────────────────────────────────
    # team sub-commands
    # ────────────────────────────────────────────────────────────────────
    async def team_view(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        async with get_session() as s:
            user = await s.get(User, str(inter.user.id))
            ids = [
                user.active_esprit_id,
                user.support1_esprit_id,
                user.support2_esprit_id,
            ]
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id.in_(ids))
                .options(selectinload(UserEsprit.esprit_data))
            )
            esprits = {e.id: e for e in (await s.execute(stmt)).scalars().all()}

        labels = ["Leader", "Support-1", "Support-2"]
        lines = []
        for label, _id in zip(labels, ids):
            if not _id:
                lines.append(f"**{label}:** —")
            elif _id in esprits:
                e = esprits[_id]
                lines.append(
                    f"**{label}:** {e.esprit_data.name} (Lvl {e.current_level}, Sigil {e.calculate_power():,})"
                )
            else:
                lines.append(f"**{label}:** (missing)")
        await inter.followup.send(
            embed=discord.Embed(title="🛡️ Team", description="\n".join(lines)),
            ephemeral=True,
        )

    async def team_set(
        self,
        inter: discord.Interaction,
        slot: TeamSlot,
        esprit_id: str,
    ):
        if slot not in {1, 2, 3}:
            return await inter.response.send_message("Slot 1-3.", ephemeral=True)
        await inter.response.defer(ephemeral=True)

        async with get_session() as s:
            ue = await s.get(UserEsprit, esprit_id)
            if not ue or ue.owner_id != str(inter.user.id):
                return await inter.followup.send("Bad ID / not yours.", ephemeral=True)

            user = await s.get(User, str(inter.user.id))
            if slot.value == 1:
                user.active_esprit_id = esprit_id
            elif slot.value == 2:
                user.support1_esprit_id = esprit_id
            else:
                user.support2_esprit_id = esprit_id

            await s.commit()
        await inter.followup.send("✅ Team updated.", ephemeral=True)

    async def team_optimize(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        esprits = await self._get_collection(str(inter.user.id))
        best = sorted(esprits, key=lambda e: e.calculate_power(), reverse=True)[:3]
        if len(best) < 3:
            return await inter.followup.send("Need 3+ Esprits.", ephemeral=True)

        async with get_session() as s:
            user = await s.get(User, str(inter.user.id))
            user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id = (
                e.id for e in best
            )
            await s.commit()
        await self._invalidate(str(inter.user.id))
        await inter.followup.send(
            "✅ Team optimized to highest Sigil.", ephemeral=True
        )

    # ────────────────────────────────────────────────────────────────────
    # util
    # ────────────────────────────────────────────────────────────────────
    def _rarity_color(self, rarity: str) -> discord.Color:
        return {
            "Common": discord.Color.light_grey(),
            "Uncommon": discord.Color.green(),
            "Rare": discord.Color.blue(),
            "Epic": discord.Color.purple(),
            "Celestial": discord.Color.gold(),
            "Supreme": discord.Color.red(),
            "Deity": discord.Color.from_rgb(255, 20, 147),
        }.get(rarity, discord.Color.default())

    def _rarity_emoji(self, rarity: str) -> str:
        return {
            "Common": "⚪",
            "Uncommon": "🟢",
            "Rare": "🔵",
            "Epic": "🟣",
            "Celestial": "🟡",
            "Supreme": "🔴",
            "Deity": "🌟",
        }.get(rarity, "❓")


# ────────────────────────────────────────────────────────────────────────────
# Cog wrapper
# ────────────────────────────────────────────────────────────────────────────
class EspritCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = EspritGroup(bot)

    async def cog_load(self):
        self.bot.tree.add_command(self.group)
        logger.info("EspritCog loaded.")

    async def cog_unload(self):
        self.bot.tree.remove_command(self.group.name)
        logger.info("EspritCog unloaded.")


async def setup(bot: commands.Bot):
    await bot.add_cog(EspritCog(bot))
    logger.info("✅ EspritCog loaded.")
