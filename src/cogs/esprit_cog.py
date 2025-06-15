# src/cogs/esprit_cog.py
import asyncio
import traceback
from typing import List, Optional, Dict, Set
import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiter
from src.utils.cache_manager import CacheManager
from src.utils.transaction_logger import (
    log_limit_break,
    log_esprit_upgrade,
    log_esprit_dissolve,
    log_esprit_search,
    log_esprit_compare,
    log_team_optimize,
)
from enum import Enum

logger = get_logger(__name__)

MAX_COLLECTION_PAGE_SIZE = 25
CACHE_TTL = 300
INTERACTION_TIMEOUT = 180
MAX_BULK_OPERATIONS = 10

class TeamSlot(Enum):
    leader   = "active_esprit_id"
    support1 = "support1_esprit_id"
    support2 = "support2_esprit_id"

# ─── Confirmation View ─────────────────────────────────────────────────────

class ConfirmationView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: Optional[bool] = None

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.author_id:
            await i.response.send_message("This prompt isn’t for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, i: discord.Interaction, _):
        self.value = True
        self.stop()
        await i.response.edit_message(content="✅ Confirmed", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, i: discord.Interaction, _):
        self.value = False
        self.stop()
        await i.response.edit_message(content="❌ Cancelled", view=None)

class BulkDissolveView(discord.ui.View):
    """Interactive multi-dissolve selection."""
    def __init__(self, esprits: List[UserEsprit], author_id: int):
        super().__init__(timeout=300)
        self.esprits = esprits[:MAX_BULK_OPERATIONS]
        self.author_id = author_id
        self.selected_ids: Set[str] = set()
        self._refresh_options()

    def _rarity_emoji(self, r: str) -> str:
        return {
            "Common": "⚪", "Uncommon": "🟢", "Rare": "🔵",
            "Epic": "🟣", "Celestial": "🟡", "Supreme": "🔴",
            "Deity": "🌟"
        }.get(r, "❓")

    def _refresh_options(self) -> None:
        try:
            opts: List[discord.SelectOption] = []
            for e in self.esprits:
                emoji = self._rarity_emoji(e.esprit_data.rarity)
                opts.append(
                    discord.SelectOption(
                        label=f"{e.esprit_data.name} • Lvl {e.current_level}",
                        value=e.id,
                        emoji=emoji,
                        description=f"{e.esprit_data.rarity} | ID:{e.id[:8]}"
                    )
                )
            self.select_menu.options = opts
            self.dissolve_button.disabled = not self.selected_ids
        except Exception as e:
            logger.error(f"Error refreshing bulk dissolve options: {e}")

    @discord.ui.select(
        placeholder="Select Esprits to dissolve…",
        min_values=0, max_values=MAX_BULK_OPERATIONS
    )
    async def select_menu(self, inter: discord.Interaction, select: discord.ui.Select):
        try:
            self.selected_ids = set(select.values)
            self.dissolve_button.disabled = not self.selected_ids
            await inter.response.edit_message(view=self)
        except Exception as e:
            logger.error(f"Error in bulk dissolve select: {e}")

    @discord.ui.button(
        label="Dissolve Selected",
        style=discord.ButtonStyle.danger,
        disabled=True
    )
    async def dissolve_button(self, inter: discord.Interaction, _: discord.ui.Button):
        try:
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
        except Exception as e:
            logger.error(f"Error in dissolve button: {e}")

    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Not your session.", ephemeral=True)
            return False
        return True
    
# ─── Collection View ────────────────────────────────────────────────────────

class EnhancedCollectionView(discord.ui.View):
    def __init__(
        self,
        esprits: List[UserEsprit],
        author_id: int,
        power_cfg: Dict,
        stat_cfg: Dict
    ):
        super().__init__(timeout=INTERACTION_TIMEOUT)
        self.author_id = author_id
        self.all_esprits = esprits
        self.power_cfg = power_cfg
        self.stat_cfg = stat_cfg
        self.filtered = list(esprits)
        self.page = 0
        self.sort_by = "name"
        self.filter_rarity: Optional[str] = None
        self.page_size = 10
        self._build_pages()
        self._update_buttons()

    def _build_pages(self):
        # Filter
        if self.filter_rarity:
            self.filtered = [e for e in self.all_esprits if e.esprit_data.rarity == self.filter_rarity]
        else:
            self.filtered = list(self.all_esprits)
        # Sort
        if self.sort_by == "name":
            self.filtered.sort(key=lambda e: e.esprit_data.name)
        elif self.sort_by == "level":
            self.filtered.sort(key=lambda e: e.current_level, reverse=True)
        else:
            order = {"Common":0,"Uncommon":1,"Rare":2,"Epic":3,"Celestial":4,"Supreme":5,"Deity":6}
            self.filtered.sort(key=lambda e: order.get(e.esprit_data.rarity,0), reverse=True)

        # Build embeds
        self.pages: List[discord.Embed] = []
        total = len(self.filtered)
        if total == 0:
            self.pages.append(
                discord.Embed(
                    title="📦 Your Esprit Arsenal",
                    description="No Esprits match these filters.",
                    color=discord.Color.light_grey()
                )
            )
            return

        total_power = sum(e.calculate_power(self.power_cfg, self.stat_cfg) for e in self.filtered)
        for i in range(0, total, self.page_size):
            chunk = self.filtered[i:i+self.page_size]
            em = discord.Embed(
                title="📦 Your Esprit Arsenal",
                description=(
                    f"Total: **{total}** | Sigil Power: **{total_power:,}**\n"
                    f"Page {i//self.page_size + 1}/{(total-1)//self.page_size +1}"
                ),
                color=discord.Color.dark_gold()
            )
            for ue in chunk:
                name = ue.esprit_data.name
                lvl = ue.current_level
                cap = ue.get_current_level_cap(self.bot.config_manager.get_config("data/config/progression_settings").get("progression", {}))
                power = ue.calculate_power(self.power_cfg, self.stat_cfg)
                rarity = ue.esprit_data.rarity
                emoji = {"Common":"⚪","Uncommon":"🟢","Rare":"🔵","Epic":"🟣","Celestial":"🟡","Supreme":"🔴","Deity":"🌟"}.get(rarity,"❓")
                em.add_field(
                    name=f"{emoji} {name}",
                    value=f"ID `{ue.id}` | Lvl **{lvl}/{cap}** | Sigil **{power:,}**",
                    inline=False
                )
            self.pages.append(em)

    def _update_buttons(self):
        for b in (self.first, self.prev, self.next, self.last):
            b.disabled = False
        self.first.disabled = self.page == 0
        self.prev.disabled  = self.page == 0
        self.next.disabled  = self.page >= len(self.pages)-1
        self.last.disabled  = self.page >= len(self.pages)-1

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.author_id:
            await i.response.send_message("Not your view.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first(self, i: discord.Interaction, _):
        self.page = 0; self._update_buttons(); await i.response.edit_message(embed=self.pages[self.page], view=self)
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev(self, i: discord.Interaction, _):
        self.page -= 1; self._update_buttons(); await i.response.edit_message(embed=self.pages[self.page], view=self)
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, i: discord.Interaction, _):
        self.page += 1; self._update_buttons(); await i.response.edit_message(embed=self.pages[self.page], view=self)
    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last(self, i: discord.Interaction, _):
        self.page = len(self.pages)-1; self._update_buttons(); await i.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.select(
        placeholder="Sort by…",
        options=[
            discord.SelectOption(label="Name",   value="name",   emoji="📝"),
            discord.SelectOption(label="Level",  value="level",  emoji="📈"),
            discord.SelectOption(label="Rarity", value="rarity", emoji="💎"),
        ]
    )
    async def sort(self, i: discord.Interaction, sel: discord.ui.Select):
        self.sort_by = sel.values[0]
        self.page = 0
        self._build_pages(); self._update_buttons()
        await i.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.select(
        placeholder="Filter rarity…",
        options=[discord.SelectOption(label="All", value="all", emoji="🌟")] + [
            discord.SelectOption(label=r, value=r, emoji=e) for r,e in
            [("Common","⚪"),("Uncommon","🟢"),("Rare","🔵"),("Epic","🟣"),
             ("Celestial","🟡"),("Supreme","🔴"),("Deity","🌟")]
        ]
    )
    async def filter(self, i: discord.Interaction, sel: discord.ui.Select):
        self.filter_rarity = None if sel.values[0]=="all" else sel.values[0]
        self.page = 0
        self._build_pages(); self._update_buttons()
        await i.response.edit_message(embed=self.pages[self.page], view=self)

# ─── Slash Commands Group ──────────────────────────────────────────────────

@app_commands.guild_only()
class EspritGroup(app_commands.Group, name="esprit"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.cache = CacheManager(default_ttl=CACHE_TTL)
        self.rate_limiter = RateLimiter(calls=5, period=60)
        self.config_manager = bot.config_manager
        
        self.combat_settings = self.config_manager.get_config('data/config/combat_settings') or {}
        self.progression_settings = self.config_manager.get_config('data/config/progression_settings') or {}

    async def _handle_error(self, inter: discord.Interaction, error: Exception):
        err_id = id(error)
        logger.error(f"[{err_id}] {error}", exc_info=True)
        if not inter.response.is_done():
            await inter.response.send_message(f"❌ Something went wrong (ID `{err_id}`).", ephemeral=True)
        else:
            await inter.followup.send(f"❌ Something went wrong (ID `{err_id}`).", ephemeral=True)

    async def _check_rl(self, inter: discord.Interaction) -> bool:
        ok = await self.rate_limiter.check(str(inter.user.id))
        if not ok:
            wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
            await inter.followup.send(f"⏳ Slow down! Try again in {wait}s.", ephemeral=True)
        return ok

    async def _ensure_user(self, user_id: str):
        async with get_session() as s:
            if not await s.get(User, user_id):
                s.add(User(user_id=user_id, username="Unknown"))
                await s.commit()

    async def _get_collection(self, user_id: str) -> List[UserEsprit]:
        await self._ensure_user(user_id)
        async with get_session() as s:
            res = await s.execute(
                select(UserEsprit)
                .where(UserEsprit.owner_id==user_id)
                .options(selectinload(UserEsprit.esprit_data))
            )
            return res.scalars().all()

    async def _invalidate_cache(self, user_id: str):
        try:
            await self.cache.clear_pattern(f"user:{user_id}:")
        except Exception as e:
            logger.warning(f"Cache clear failed for {user_id}: {e}")

    @app_commands.command(name="collection", description="Browse your collected Esprits.")
    async def collection(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            esprits = await self._get_collection(str(inter.user.id))
            if not esprits:
                return await inter.followup.send(
                    embed=discord.Embed(
                        title="🌱 No Esprits Yet",
                        description="Use `/summon` to acquire your first companion!",
                        color=discord.Color.blue()
                    ), ephemeral=True
                )

            view = EnhancedCollectionView(
                esprits,
                inter.user.id,
                power_cfg=self.cfg.get("power_calculation", {}),
                stat_cfg=self.cfg.get("stat_calculation", {})
            )
            await inter.followup.send(embed=view.pages[0], view=view, ephemeral=True)

        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="details", description="Show full stats for one Esprit.")
    @app_commands.describe(esprit_id="The ID from your collection.")
    async def details(self, inter: discord.Interaction, esprit_id: str):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            async with get_session() as s:
                ue = await s.get(UserEsprit, esprit_id,
                    options=[selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner)]
                )
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Not found or not yours.", ephemeral=True)

            prog      = self.cfg.get("progression", {})
            stat_cfg  = self.cfg.get("stat_calculation", {})
            power_cfg = self.cfg.get("power_calculation", {})
            lb_cfg    = self.cfg.get("limit_break_system", {})
            up_cfg    = self.cfg.get("esprit_upgrade_system", {})

            cap   = ue.get_current_level_cap(prog)
            power = ue.calculate_power(power_cfg, stat_cfg)
            hp    = ue.calculate_stat("hp", stat_cfg)
            atk   = ue.calculate_stat("attack", stat_cfg)
            df    = ue.calculate_stat("defense", stat_cfg)
            spd   = ue.calculate_stat("speed", stat_cfg)
            mr    = ue.calculate_stat("magic_resist", stat_cfg)
            ed    = ue.esprit_data

            embed = discord.Embed(
                title=f"🔎 {ed.name} — Lv {ue.current_level}/{cap}",
                description="“Every sigil tells a story…”",
                color=discord.Color.purple()
            )
            embed.add_field(name="Power", value=f"💥 {power:,}", inline=True)
            embed.add_field(name="HP", value=f"{hp:,}", inline=True)
            embed.add_field(name="ATK", value=f"{atk:,}", inline=True)
            embed.add_field(name="DEF", value=f"{df:,}", inline=True)
            embed.add_field(name="SPD", value=f"{spd:,}", inline=True)
            embed.add_field(name="MR",  value=f"{mr:,}", inline=True)

            # Next upgrade or limit break
            if ue.current_level < cap:
                cost = eval(up_cfg.get("cost_formula","15+(lvl*8)"),{"lvl":ue.current_level})
                embed.add_field(name="⚡ Next Upgrade", value=f"{cost:,} Virelite", inline=True)
            else:
                can = ue.can_limit_break(prog)
                if can["can_break"]:
                    c = ue.get_limit_break_cost(lb_cfg)
                    embed.add_field(
                        name="🔓 Limit Break",
                        value=f"{c['remna']:,} Remna + {c['virelite']:,} Virelite",
                        inline=True
                    )
                else:
                    embed.add_field(name="🔒 Locked", value="Reach higher player level to unlock.", inline=True)

            await inter.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="limitbreak", description="Break through an Esprit’s level cap.")
    @app_commands.describe(esprit_id="ID of the Esprit to break.")
    async def limitbreak(self, inter: discord.Interaction, esprit_id: str):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            prog      = self.cfg.get("progression", {})
            lb_cfg    = self.cfg.get("limit_break_system", {})
            stat_cfg  = self.cfg.get("stat_calculation", {})
            power_cfg = self.cfg.get("power_calculation", {})

            if not lb_cfg.get("enabled", False):
                return await inter.followup.send("❌ Limit breaks are disabled.", ephemeral=True)

            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                ue   = await s.get(UserEsprit, esprit_id, with_for_update=True,
                    options=[selectinload(UserEsprit.esprit_data)]
                )
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Not found or not yours.", ephemeral=True)

                can = ue.can_limit_break(prog)
                if not can["can_break"]:
                    return await inter.followup.send(f"❌ {can['reason'].replace('_',' ').capitalize()}.", ephemeral=True)

                cost = ue.get_limit_break_cost(lb_cfg)
                if user.remna < cost["remna"] or user.virelite < cost["virelite"]:
                    return await inter.followup.send("❌ Insufficient materials.", ephemeral=True)

                old = ue.calculate_power(power_cfg, stat_cfg)
                user.remna    -= cost["remna"]
                user.virelite -= cost["virelite"]
                ue.limit_breaks_performed += 1
                ue.stat_boost_multiplier *= lb_cfg.get("compound_rate",1.1)
                ue.current_hp = ue.calculate_stat("hp", stat_cfg)
                await s.commit()

            new_embed = discord.Embed(
                title="🔓 LIMIT BREAK!",
                description=f"Your **{ue.esprit_data.name}** has transcended its limits.",
                color=discord.Color.gold()
            )
            new_embed.add_field(name="Power", value=f"{old:,} → **{ue.calculate_power(power_cfg, stat_cfg):,}**", inline=True)
            new_embed.add_field(name="Total Breaks", value=str(ue.limit_breaks_performed), inline=True)
            await inter.followup.send(embed=new_embed, ephemeral=True)
            log_limit_break(inter, ue, cost)
            await self._invalidate_cache(str(inter.user.id))

        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="upgrade", description="Spend Virelite to level up an Esprit.")
    @app_commands.describe(esprit_id="ID of the Esprit", levels="How many levels (1-10 or 'max').")
    async def upgrade(self, inter: discord.Interaction, esprit_id: str, levels: str):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            prog      = self.cfg.get("progression", {})
            up_cfg    = self.cfg.get("esprit_upgrade_system", {})
            stat_cfg  = self.cfg.get("stat_calculation", {})
            power_cfg = self.cfg.get("power_calculation", {})

            if not up_cfg.get("enabled", True):
                return await inter.followup.send("❌ Upgrades are disabled.", ephemeral=True)

            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                ue   = await s.get(UserEsprit, esprit_id, with_for_update=True,
                    options=[selectinload(UserEsprit.esprit_data)]
                )
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Not found or not yours.", ephemeral=True)

                cap = ue.get_current_level_cap(prog)
                if ue.current_level >= cap:
                    return await inter.followup.send(
                        f"❌ Already at cap ({cap}). Use `/esprit limitbreak` to raise it.",
                        ephemeral=True
                    )

                max_add = cap - ue.current_level
                if levels.lower() == "max":
                    add = max_add
                else:
                    try:
                        n = int(levels)
                        if not (1 <= n <= 10): raise ValueError()
                        add = min(n, max_add)
                    except:
                        return await inter.followup.send("❌ Levels must be 1–10 or 'max'.", ephemeral=True)

                if add == 0:
                    return await inter.followup.send("❌ No levels to add.", ephemeral=True)

                cost_formula = up_cfg.get("cost_formula", "15+(lvl*8)")
                total_cost = sum(
                    eval(cost_formula, {"lvl":lvl})
                    for lvl in range(ue.current_level, ue.current_level+add)
                )
                if user.virelite < total_cost:
                    return await inter.followup.send(
                        f"❌ Need {total_cost:,} Virelite (you have {user.virelite:,}).",
                        ephemeral=True
                    )

                old_pow = ue.calculate_power(power_cfg, stat_cfg)
                user.virelite -= total_cost
                ue.current_level += add
                ue.current_hp = ue.calculate_stat("hp", stat_cfg)
                await s.commit()

            new_pow = ue.calculate_power(power_cfg, stat_cfg)
            embed = discord.Embed(
                title="⭐ Upgrade Complete!",
                description=f"**{ue.esprit_data.name}** → Level **{ue.current_level}**",
                color=discord.Color.gold()
            )
            embed.add_field(name="Levels Gained", value=f"+{add}")
            embed.add_field(name="Virelite Spent", value=f"{total_cost:,}")
            embed.add_field(name="Power", value=f"{old_pow:,} → **{new_pow:,}**")
            await inter.followup.send(embed=embed, ephemeral=True)
            log_esprit_upgrade(inter, ue, old_pow, total_cost)
            await self._invalidate_cache(str(inter.user.id))

        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="dissolve", description="Recycle Esprit(s) for resources.")
    @app_commands.describe(
        esprit_id="ID to dissolve (omit for bulk)",
        multi="Use bulk mode",
        rarity_filter="Filter in bulk"
    )
    async def dissolve(
        self,
        inter: discord.Interaction,
        esprit_id: Optional[str] = None,
        multi: bool = False,
        rarity_filter: Optional[str] = None
    ):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            rewards_cfg = self.cfg.get("dissolve_rewards", {})

            # Bulk
            if multi:
                valid = {"Common","Uncommon","Rare","Epic","Celestial","Supreme","Deity"}
                if rarity_filter and rarity_filter not in valid:
                    return await inter.followup.send("❌ Invalid rarity filter.", ephemeral=True)

                async with get_session() as s:
                    user = await s.get(User, str(inter.user.id))
                    protected = {
                        user.active_esprit_id,
                        user.support1_esprit_id,
                        user.support2_esprit_id
                    } - {None}
                    stmt = select(UserEsprit).where(
                        and_(
                            UserEsprit.owner_id==str(inter.user.id),
                            ~UserEsprit.id.in_(protected)
                        )
                    ).options(selectinload(UserEsprit.esprit_data))
                    if rarity_filter:
                        stmt = stmt.where(UserEsprit.esprit_data.has(rarity=rarity_filter))
                    esprits = (await s.execute(stmt)).scalars().all()

                if not esprits:
                    return await inter.followup.send("❌ Nothing to dissolve.", ephemeral=True)

                view = BulkDissolveView(esprits, inter.user.id)
                await inter.followup.send(
                    embed=discord.Embed(
                        title="♻️ Bulk Dissolve",
                        description="Select up to 10 Esprits to dissolve.",
                        color=discord.Color.orange()
                    ),
                    view=view, ephemeral=True
                )
                await view.wait()
                if not view.value:
                    return  # cancelled
                ids = view.selected_ids

                async with get_session() as s:
                    user = await s.get(User, str(inter.user.id), with_for_update=True)
                    stmt = select(UserEsprit).where(UserEsprit.id.in_(ids)).options(selectinload(UserEsprit.esprit_data))
                    to_del = (await s.execute(stmt)).scalars().all()
                    totals = {"virelite":0,"remna":0}
                    for e in to_del:
                        r = rewards_cfg.get(e.esprit_data.rarity, {})
                        totals["virelite"] += r.get("virelite",0)
                        totals["remna"]    += r.get("remna",0)
                        await s.delete(e)
                    user.virelite += totals["virelite"]
                    user.remna     += totals["remna"]
                    await s.commit()

                embed = discord.Embed(
                    title="♻️ Bulk Dissolve Complete",
                    description=(
                        f"Dissolved **{len(to_del)}** Esprits.\n"
                        f"Rewards: {totals['virelite']:,} Virelite, {totals['remna']:,} Remna"
                    ),
                    color=discord.Color.green()
                )
                await inter.followup.send(embed=embed, ephemeral=True)
                log_esprit_dissolve(inter, to_del, totals)
                await self._invalidate_cache(str(inter.user.id))
                return

            # Single
            if not esprit_id:
                return await inter.followup.send("❌ Provide an `esprit_id` or set `multi=True`.", ephemeral=True)

            async with get_session() as s:
                ue = await s.get(UserEsprit, esprit_id, options=[selectinload(UserEsprit.esprit_data)])
                user = await s.get(User, str(inter.user.id))
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Not found or not yours.", ephemeral=True)
                if esprit_id in {user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id}:
                    return await inter.followup.send("❌ Cannot dissolve a team member.", ephemeral=True)

            confirm = ConfirmationView(inter.user.id)
            await inter.followup.send(
                embed=discord.Embed(
                    title="⚠️ Confirm Dissolve",
                    description=f"Dissolve **{ue.esprit_data.name}** (Lv {ue.current_level})?",
                    color=discord.Color.orange()
                ),
                view=confirm, ephemeral=True
            )
            await confirm.wait()
            if not confirm.value:
                return

            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                r = rewards_cfg.get(ue.esprit_data.rarity, {})
                user.virelite += r.get("virelite",0)
                user.remna     += r.get("remna",0)
                await s.delete(ue)
                await s.commit()

            embed = discord.Embed(
                title="♻️ Dissolved",
                description=f"Received: **{r.get('virelite',0):,}** Virelite, **{r.get('remna',0):,}** Remna",
                color=discord.Color.green()
            )
            await inter.followup.send(embed=embed, ephemeral=True)
            log_esprit_dissolve(inter, [ue], r)
            await self._invalidate_cache(str(inter.user.id))

        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="search", description="Search your Esprits by name.")
    @app_commands.describe(query="Part of an Esprit’s name.")
    async def search(self, inter: discord.Interaction, query: str):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            esprits = await self._get_collection(str(inter.user.id))
            results = [e for e in esprits if query.lower() in e.esprit_data.name.lower()][:25]
            if not results:
                return await inter.followup.send("❌ No matches found.", ephemeral=True)

            prog      = self.cfg.get("progression", {})
            stat_cfg  = self.cfg.get("stat_calculation", {})
            power_cfg = self.cfg.get("power_calculation", {})
            lines = []
            for e in results:
                cap = e.get_current_level_cap(prog)
                p   = e.calculate_power(power_cfg, stat_cfg)
                lines.append(f"`{e.id}` • {e.esprit_data.name} • Lv {e.current_level}/{cap} • Sigil {p:,}")

            text = "\n".join(lines)
            await inter.followup.send(
                embed=discord.Embed(
                    title=f"🔍 Search Results ({len(results)})",
                    description=text[:4000] + ("…" if len(text)>4000 else "")
                ),
                ephemeral=True
            )
            log_esprit_search(inter, query, results)

        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="compare", description="Compare two Esprits’ stats.")
    @app_commands.describe(esprit_a="First ID", esprit_b="Second ID")
    async def compare(self, inter: discord.Interaction, esprit_a: str, esprit_b: str):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return
            if esprit_a == esprit_b:
                return await inter.followup.send("❌ Provide two different IDs.", ephemeral=True)

            prog      = self.cfg.get("progression", {})
            stat_cfg  = self.cfg.get("stat_calculation", {})
            power_cfg = self.cfg.get("power_calculation", {})

            async with get_session() as s:
                rows = (await s.execute(
                    select(UserEsprit)
                    .where(UserEsprit.id.in_([esprit_a, esprit_b]))
                    .options(selectinload(UserEsprit.esprit_data))
                )).scalars().all()

            if len(rows)!=2 or any(r.owner_id!=str(inter.user.id) for r in rows):
                return await inter.followup.send("❌ Invalid IDs or not yours.", ephemeral=True)

            a,b = {r.id:r for r in rows}[esprit_a], {r.id:r for r in rows}[esprit_b]
            embed = discord.Embed(
                title="⚖️ Esprit Comparison",
                description="“Strength is measured in sigils.”",
                color=discord.Color.dark_teal()
            )
            for ue in (a,b):
                cap   = ue.get_current_level_cap(prog)
                power = ue.calculate_power(power_cfg, stat_cfg)
                rarity = ue.esprit_data.rarity
                emoji = {"Common":"⚪","Uncommon":"🟢","Rare":"🔵","Epic":"🟣","Celestial":"🟡","Supreme":"🔴","Deity":"🌟"}.get(rarity,"❓")
                embed.add_field(
                    name=f"{emoji} {ue.esprit_data.name}",
                    value=(f"Sigil: **{power:,}**\nLvl: **{ue.current_level}/{cap}**"),
                    inline=False
                )

            await inter.followup.send(embed=embed, ephemeral=True)
            log_esprit_compare(inter, a, b)

        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="team", description="View your combat team.")
    async def team_view(self, inter: discord.Interaction):
        try:
            await inter.response.defer()  # public
            if not await self._check_rl(inter): return

            prog      = self.cfg.get("progression", {})
            stat_cfg  = self.cfg.get("stat_calculation", {})
            power_cfg = self.cfg.get("power_calculation", {})

            async with get_session() as s:
                user = await s.get(User, str(inter.user.id))
                ids = [user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id]
                valid = [i for i in ids if i]
                rows  = (await s.execute(
                    select(UserEsprit).where(UserEsprit.id.in_(valid))
                    .options(selectinload(UserEsprit.esprit_data))
                )).scalars().all()
                m = {e.id:e for e in rows}

            embed = discord.Embed(
                title="🛡️ Your Combat Team",
                description="“Forge your sigils into steel.”",
                color=discord.Color.dark_green()
            )
            total = 0
            labels = ["Leader","Support 1","Support 2"]
            for lab, eid in zip(labels, ids):
                if not eid or eid not in m:
                    embed.add_field(name=lab, value="— *Empty Slot* —", inline=False)
                else:
                    ue = m[eid]
                    p  = ue.calculate_power(power_cfg, stat_cfg)
                    total += p
                    embed.add_field(
                        name=f"**{lab}:** {ue.esprit_data.name}",
                        value=f"Lvl {ue.current_level} • Sigil {p:,}",
                        inline=False
                    )
            embed.set_footer(text=f"Total Sigil Power: {total:,}")
            await inter.followup.send(embed=embed)
        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="team_set", description="Assign an Esprit to your team.")
    @app_commands.describe(slot="Which slot", esprit_id="Esprit ID")
    async def team_set(self, inter: discord.Interaction, slot: TeamSlot, esprit_id: str):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            async with get_session() as s:
                ue = await s.get(UserEsprit, esprit_id)
                user = await s.get(User, str(inter.user.id))
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Not found or not yours.", ephemeral=True)
                setattr(user, slot.value, esprit_id)
                await s.commit()

            await inter.followup.send(f"✅ {slot.name.title()} set to {ue.esprit_data.name}.", ephemeral=True)
        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="team_optimize", description="Auto-optimize your top 3 Esprits.")
    async def team_optimize(self, inter: discord.Interaction):
        try:
            await inter.response.defer()  # public
            if not await self._check_rl(inter): return

            stat_cfg  = self.cfg.get("stat_calculation", {})
            power_cfg = self.cfg.get("power_calculation", {})

            esprits = await self._get_collection(str(inter.user.id))
            if len(esprits) < 3:
                return await inter.followup.send("❌ Need at least 3 Esprits.", ephemeral=True)

            # sort by power
            def pwr(e): return e.calculate_power(power_cfg, stat_cfg)
            best = sorted(esprits, key=pwr, reverse=True)[:3]

            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                slots = ["active_esprit_id","support1_esprit_id","support2_esprit_id"]
                for slot, ue in zip(slots, best):
                    setattr(user, slot, ue.id)
                await s.commit()

            lines = []
            icons = ["👑","⚔️","⚔️"]
            for icon, ue in zip(icons, best):
                lines.append(f"{icon} {ue.esprit_data.name} • Sigil {pwr(ue):,}")

            embed = discord.Embed(
                title="✅ Team Optimized!",
                description="\n".join(lines),
                color=discord.Color.green()
            )
            await inter.followup.send(embed=embed)
            log_team_optimize(inter, best)
        except Exception as e:
            await self._handle_error(inter, e)

# ─── Cog Loader ──────────────────────────────────────────────────────────────

class EspritCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = EspritGroup(bot)

    async def cog_load(self):
        self.bot.tree.add_command(self.group)
        logger.info("✅ EspritCog loaded.")

    async def cog_unload(self):
        self.bot.tree.remove_command(self.group.name)
        logger.info("🛑 EspritCog unloaded.")

async def setup(bot: commands.Bot):
    await bot.add_cog(EspritCog(bot))
    logger.info("✅ EspritCog setup complete.")

