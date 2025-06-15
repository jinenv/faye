# src/cogs/esprit_cog.py
import asyncio
import traceback
from typing import List, Literal, Optional, Dict, Set
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
        self.result = False

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.author_id:
            await i.response.send_message("This prompt isn’t for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, i: discord.Interaction, _):
        self.value = True
        self.result = True
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
        self.value = False # To indicate confirmation
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
        min_values=0, max_values=MAX_BULK_OPERATIONS,
        row=0
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
        disabled=True,
        row=1
    )
    async def dissolve_button(self, inter: discord.Interaction, _: discord.ui.Button):
        try:
            if not self.selected_ids:
                return await inter.response.send_message("You must select at least one Esprit.", ephemeral=True)

            confirm_view = ConfirmationView(self.author_id)
            await inter.response.send_message(
                embed=discord.Embed(
                    title="⚠️ Confirm Bulk Dissolve",
                    description=f"Are you sure you want to dissolve **{len(self.selected_ids)}** Esprit(s)? This cannot be undone.",
                    color=discord.Color.red(),
                ),
                view=confirm_view,
                ephemeral=True,
            )
            await confirm_view.wait()
            if confirm_view.value:
                self.value = True
                self.stop()
        except Exception as e:
            logger.error(f"Error in dissolve button: {e}")
            await inter.followup.send("An error occurred during confirmation.", ephemeral=True)

    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("This is not your session.", ephemeral=True)
            return False
        return True

# ─── Collection View ────────────────────────────────────────────────────────

class EnhancedCollectionView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        esprits: List[UserEsprit],
        author_id: int,
    ):
        super().__init__(timeout=INTERACTION_TIMEOUT)
        self.bot = bot
        self.author_id = author_id
        self.all_esprits = esprits
        self.power_cfg = self.bot.config.get("combat_settings", {}).get("power_calculation", {})
        self.stat_cfg = self.bot.config.get("combat_settings", {}).get("stat_calculation", {})
        self.prog_cfg = self.bot.config.get("progression_settings", {}).get("progression", {})
        self.filtered = list(esprits)
        self.page = 0
        self.sort_by = "rarity" # Default sort
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
        elif self.sort_by == "power":
             self.filtered.sort(key=lambda e: e.calculate_power(self.power_cfg, self.stat_cfg), reverse=True)
        else: # Default to rarity
            order = {"Common":0,"Uncommon":1,"Rare":2,"Epic":3,"Celestial":4,"Supreme":5,"Deity":6}
            self.filtered.sort(key=lambda e: order.get(e.esprit_data.rarity, 0), reverse=True)

        # Build embeds
        self.pages: List[discord.Embed] = []
        total = len(self.filtered)
        if total == 0:
            self.pages.append(
                discord.Embed(
                    title="📦 Your Esprit Arsenal",
                    description="No Esprits match the current filters.",
                    color=discord.Color.light_grey()
                )
            )
            return

        total_power = sum(e.calculate_power(self.power_cfg, self.stat_cfg) for e in self.all_esprits)
        for i in range(0, total, self.page_size):
            chunk = self.filtered[i:i+self.page_size]
            em = discord.Embed(
                title="📦 Your Esprit Arsenal",
                description=(
                    f"Total Esprits: **{len(self.all_esprits)}** | Total Sigil Power: **{total_power:,}**\n"
                    f"Showing: **{total}** (Page {i//self.page_size + 1}/{(total + self.page_size - 1)//self.page_size})"
                ),
                color=discord.Color.dark_gold()
            )
            for ue in chunk:
                name = ue.esprit_data.name
                lvl = ue.current_level
                # This logic should be on the model, but for now we pass prog_cfg
                cap = ue.get_level_cap(self.prog_cfg)
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
        # Check if pages exist
        if not self.pages or len(self.pages) <= 1:
            self.first.disabled = True
            self.prev.disabled = True
            self.next.disabled = True
            self.last.disabled = True
            return

        self.first.disabled = self.page == 0
        self.prev.disabled  = self.page == 0
        self.next.disabled  = self.page >= len(self.pages)-1
        self.last.disabled  = self.page >= len(self.pages)-1

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.author_id:
            await i.response.send_message("This is not your view.", ephemeral=True)
            return False
        return True

    async def _update_view(self, i: discord.Interaction):
        self._build_pages()
        self._update_buttons()
        await i.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first(self, i: discord.Interaction, _):
        self.page = 0
        await self._update_view(i)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev(self, i: discord.Interaction, _):
        self.page = max(0, self.page - 1)
        await self._update_view(i)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, i: discord.Interaction, _):
        self.page = min(len(self.pages) - 1, self.page + 1)
        await self._update_view(i)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last(self, i: discord.Interaction, _):
        self.page = len(self.pages)-1
        await self._update_view(i)

    @discord.ui.select(
        placeholder="Sort by…",
        options=[
            discord.SelectOption(label="Rarity", value="rarity", emoji="💎", default=True),
            discord.SelectOption(label="Power", value="power", emoji="💥"),
            discord.SelectOption(label="Level",  value="level",  emoji="📈"),
            discord.SelectOption(label="Name",   value="name",   emoji="📝"),
        ],
        row=1
    )
    async def sort(self, i: discord.Interaction, sel: discord.ui.Select):
        self.sort_by = sel.values[0]
        self.page = 0
        await self._update_view(i)

    @discord.ui.select(
        placeholder="Filter rarity…",
        options=[discord.SelectOption(label="All", value="all", emoji="🌟")] + [
            discord.SelectOption(label=r, value=r, emoji=e) for r,e in
            [("Common","⚪"),("Uncommon","🟢"),("Rare","🔵"),("Epic","🟣"),
             ("Celestial","🟡"),("Supreme","🔴"),("Deity","🌟")]
        ],
        row=2
    )
    async def filter(self, i: discord.Interaction, sel: discord.ui.Select):
        self.filter_rarity = None if sel.values[0]=="all" else sel.values[0]
        self.page = 0
        await self._update_view(i)

# ─── Slash Commands Group ──────────────────────────────────────────────────

@app_commands.guild_only()
class EspritGroup(app_commands.Group, name="esprit"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.cache = CacheManager(default_ttl=CACHE_TTL)
        self.rate_limiter = RateLimiter(calls=5, period=60)
        
        self.combat_settings = self.bot.config.get('combat_settings', {})
        self.progression_settings = self.bot.config.get('progression_settings', {})

    async def _handle_error(self, inter: discord.Interaction, error: Exception):
        err_id = id(error)
        logger.error(f"[{err_id}] Unhandled error in EspritGroup: {error}", exc_info=True)
        # Use followup if already deferred
        if inter.response.is_done():
            await inter.followup.send(f"❌ Something went wrong (ID `{err_id}`). The developers have been notified.", ephemeral=True)
        else:
            await inter.response.send_message(f"❌ Something went wrong (ID `{err_id}`). The developers have been notified.", ephemeral=True)

    async def _check_rl(self, inter: discord.Interaction) -> bool:
        if not await self.rate_limiter.check(str(inter.user.id)):
            wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
            await inter.followup.send(f"⏳ Slow down! This command is on cooldown. Try again in {wait}s.", ephemeral=True)
            return False
        return True

    async def _get_collection(self, user_id: str) -> List[UserEsprit]:
        async with get_session() as s:
            res = await s.execute(
                select(UserEsprit)
                .where(UserEsprit.owner_id==user_id)
                .options(selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner))
            )
            return res.scalars().all()

    async def _invalidate_cache(self, user_id: str):
        await self.cache.clear_pattern(f"user:{user_id}:collection")

    @app_commands.command(name="collection", description="Browse your collected Esprits.")
    async def collection(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            esprits = await self._get_collection(str(inter.user.id))
            if not esprits:
                return await inter.followup.send(
                    embed=discord.Embed(
                        title="🌱 Your Collection is Empty",
                        description="Your journey is just beginning! Use `/summon` to acquire your first companion and start building your team.",
                        color=discord.Color.blue()
                    ), ephemeral=True
                )

            # Load necessary configs for the view
            combat_cfg = self.config_manager.get_config('data/config/combat_settings') or {}
            prog_cfg = self.config_manager.get_config('data/config/progression_settings') or {}

            view = EnhancedCollectionView(
                bot=self.bot,
                esprits=esprits,
                author_id=inter.user.id,
                power_cfg=combat_cfg.get("power_calculation", {}),
                stat_cfg=combat_cfg.get("stat_calculation", {}),
                prog_cfg=prog_cfg.get("progression", {})
            )
            await inter.followup.send(embed=view.pages[0], view=view, ephemeral=True)

        except Exception as e:
            await self._handle_error(inter, e)

    @app_commands.command(name="upgrade", description="Spend Virelite to level up an Esprit.")
    @app_commands.describe(esprit_id="ID of the Esprit", levels="How many levels (1-10 or 'max').")
    async def upgrade(self, inter: discord.Interaction, esprit_id: str, levels: str):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            prog_cfg = self.config_manager.get_config('data/config/progression_settings') or {}
            combat_cfg = self.config_manager.get_config('data/config/combat_settings') or {}
            up_cfg = combat_cfg.get("esprit_upgrade_system", {})

            async with get_session() as s:
                # --- RACE CONDITION FIX: Lock user and esprit rows for this transaction ---
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user:
                    return await inter.followup.send("❌ You need to `/start` your journey first.", ephemeral=True)

                ue = await s.get(UserEsprit, esprit_id, with_for_update=True,
                    options=[selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner)]
                )
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Esprit not found or it does not belong to you.", ephemeral=True)

                cap = ue.get_level_cap(prog_cfg.get("progression", {}))
                if ue.current_level >= cap:
                    return await inter.followup.send(
                        f"❌ **{ue.esprit_data.name}** is already at its current level cap ({cap}). Use `/esprit limitbreak` to raise it.",
                        ephemeral=True
                    )

                max_add = cap - ue.current_level
                if levels.lower() == "max":
                    add = max_add
                else:
                    try:
                        n = int(levels)
                        if not (1 <= n <= 10):
                            return await inter.followup.send("❌ Level-up amount must be between 1 and 10, or 'max'.", ephemeral=True)
                        add = min(n, max_add)
                    except ValueError:
                        return await inter.followup.send("❌ Invalid amount. Please specify a number from 1-10 or 'max'.", ephemeral=True)

                if add <= 0:
                    return await inter.followup.send(f"❌ **{ue.esprit_data.name}** is already at the level cap.", ephemeral=True)

                # --- REVISED: Safe cost calculation ---
                cost_formula = up_cfg.get("cost_formula", "15 + (current_level * 8)")
                parts = cost_formula.replace(" ", "").split('+')
                base_cost = int(parts[0])
                level_part = parts[1].replace(")", "").split('*')
                level_mult_str = level_part[1] if len(level_part) > 1 else '0'
                level_mult = int(level_mult_str)

                total_cost = sum(
                    base_cost + (lvl * level_mult)
                    for lvl in range(ue.current_level, ue.current_level + add)
                )

                if user.virelite < total_cost:
                    return await inter.followup.send(
                        f"❌ Not enough Virelite. You need **{total_cost:,}** but only have {user.virelite:,}.",
                        ephemeral=True
                    )

                old_level = ue.current_level
                old_pow = ue.calculate_power(combat_cfg.get("power_calculation", {}), combat_cfg.get("stat_calculation", {}))
                
                user.virelite -= total_cost
                ue.current_level += add
                ue.current_hp = ue.calculate_stat("hp", combat_cfg.get("stat_calculation", {}))
                
                await s.commit()
                # Refresh object to get latest data after commit
                await s.refresh(ue)
                await s.refresh(user)

            new_pow = ue.calculate_power(combat_cfg.get("power_calculation", {}), combat_cfg.get("stat_calculation", {}))
            embed = discord.Embed(
                title="⭐ Upgrade Complete!",
                description=f"**{ue.esprit_data.name}** has grown stronger!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Level", value=f"{old_level} → **{ue.current_level}**", inline=True)
            embed.add_field(name="Sigil Power", value=f"{old_pow:,} → **{new_pow:,}**", inline=True)
            embed.add_field(name="Virelite Spent", value=f"{total_cost:,}", inline=False)
            
            await inter.followup.send(embed=embed, ephemeral=True)
            
            # Log after successful transaction
            log_esprit_upgrade(inter, ue, old_level, total_cost)
            await self._invalidate_cache(str(inter.user.id))

        except Exception as e:
            await self._handle_error(inter, e)
            
    @app_commands.command(name="limitbreak", description="Break an Esprit’s level cap to unlock greater power.")
    @app_commands.describe(esprit_id="The ID of the Esprit to limit break.")
    async def limitbreak(self, inter: discord.Interaction, esprit_id: str):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            prog_cfg = self.config_manager.get_config('data/config/progression_settings') or {}
            combat_cfg = self.config_manager.get_config('data/config/combat_settings') or {}
            lb_cfg = combat_cfg.get("limit_break_system", {})

            async with get_session() as s:
                # --- RACE CONDITION FIX: Lock user and esprit rows ---
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user:
                    return await inter.followup.send("❌ You need to `/start` your journey first.", ephemeral=True)

                ue = await s.get(UserEsprit, esprit_id, with_for_update=True,
                    options=[selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner)]
                )
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Esprit not found or it does not belong to you.", ephemeral=True)

                can_break_info = ue.can_limit_break(prog_cfg.get("progression", {}))
                if not can_break_info["can_break"]:
                    return await inter.followup.send(f"❌ Cannot limit break: {can_break_info['reason']}.", ephemeral=True)

                cost = ue.get_limit_break_cost(lb_cfg)
                if user.remna < cost["remna"] or user.virelite < cost["virelite"]:
                    return await inter.followup.send(f"❌ Insufficient materials. You need **{cost['remna']:,} Remna** and **{cost['virelite']:,} Virelite**.", ephemeral=True)
                
                old_power = ue.calculate_power(combat_cfg.get("power_calculation", {}), combat_cfg.get("stat_calculation", {}))

                user.remna -= cost["remna"]
                user.virelite -= cost["virelite"]
                ue.limit_breaks_performed += 1
                ue.stat_boost_multiplier *= lb_cfg.get("compound_rate", 1.1)
                
                await s.commit()
                await s.refresh(ue)
                await s.refresh(user)
            
            new_power = ue.calculate_power(combat_cfg.get("power_calculation", {}), combat_cfg.get("stat_calculation", {}))
            embed = discord.Embed(
                title="🔓 LIMIT BREAK!",
                description=f"**{ue.esprit_data.name}** has shattered its limits!",
                color=discord.Color.gold()
            )
            embed.add_field(name="New Limit Breaks", value=f"{ue.limit_breaks_performed}", inline=True)
            embed.add_field(name="Sigil Power", value=f"{old_power:,} → **{new_power:,}**", inline=True)
            embed.add_field(name="Cost", value=f"{cost['remna']:,} Remna, {cost['virelite']:,} Virelite", inline=False)
            await inter.followup.send(embed=embed, ephemeral=True)
            
            log_limit_break(inter, ue, cost)
            await self._invalidate_cache(str(inter.user.id))
            
        except Exception as e:
            await self._handle_error(inter, e)
            
    @app_commands.command(name="dissolve", description="Recycle one or more Esprits for resources.")
    @app_commands.describe(
        esprit_id="ID of a single Esprit to dissolve (omit for bulk mode).",
        multi="Set to True to dissolve multiple Esprits at once.",
        rarity_filter="[Bulk Mode] Only show Esprits of this rarity to dissolve."
    )
    async def dissolve(self, inter: discord.Interaction, esprit_id: Optional[str] = None, multi: bool = False, rarity_filter: Optional[Literal["Common", "Uncommon", "Rare"]] = None):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return

            if multi and esprit_id:
                return await inter.followup.send("❌ You cannot use `esprit_id` with `multi=True`.", ephemeral=True)
            if not multi and not esprit_id:
                return await inter.followup.send("❌ You must either provide an `esprit_id` or set `multi=True`.", ephemeral=True)

            rewards_cfg = self.config_manager.get_config('data/config/economy_settings', {}).get("dissolve_rewards", {})

            # Bulk Dissolve
            if multi:
                async with get_session() as s:
                    user = await s.get(User, str(inter.user.id))
                    if not user:
                         return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
                    
                    team_ids = {user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id}
                    
                    query = select(UserEsprit).where(
                        UserEsprit.owner_id == str(inter.user.id),
                        UserEsprit.locked == False, # Cannot dissolve locked esprits
                        ~UserEsprit.id.in_(team_ids) # Cannot dissolve team members
                    ).options(selectinload(UserEsprit.esprit_data))
                    
                    if rarity_filter:
                        query = query.join(EspritData).where(EspritData.rarity == rarity_filter)
                        
                    esprits = (await s.execute(query)).scalars().all()

                if not esprits:
                    return await inter.followup.send("❌ No dissolvable Esprits found with the specified filters.", ephemeral=True)

                view = BulkDissolveView(esprits, inter.user.id)
                await inter.followup.send(
                    embed=discord.Embed(
                        title="♻️ Bulk Dissolve",
                        description=f"Select up to {MAX_BULK_OPERATIONS} Esprits to dissolve. Locked and team Esprits are not shown.",
                        color=discord.Color.orange()
                    ),
                    view=view, ephemeral=True
                )
                await view.wait()

                if not view.value or not view.selected_ids:
                    return # Cancelled or nothing selected

                ids_to_dissolve = view.selected_ids
                dissolved_esprits = []
                total_rewards = {"virelite": 0, "remna": 0}

                async with get_session() as s:
                    # --- RACE CONDITION FIX: Lock user row ---
                    user = await s.get(User, str(inter.user.id), with_for_update=True)
                    
                    # Fetch esprits to be deleted within the locked session
                    stmt = select(UserEsprit).where(UserEsprit.id.in_(ids_to_dissolve)).options(selectinload(UserEsprit.esprit_data))
                    to_delete = (await s.execute(stmt)).scalars().all()
                    
                    for e in to_delete:
                        reward = rewards_cfg.get(e.esprit_data.rarity, {})
                        total_rewards["virelite"] += reward.get("virelite", 0)
                        total_rewards["remna"] += reward.get("remna", 0)
                        dissolved_esprits.append(e) # For logging
                        await s.delete(e)
                        
                    user.virelite += total_rewards["virelite"]
                    user.remna += total_rewards["remna"]
                    await s.commit()

                embed = discord.Embed(
                    title="♻️ Bulk Dissolve Complete",
                    description=f"Successfully dissolved **{len(dissolved_esprits)}** Esprits.",
                    color=discord.Color.green()
                )
                embed.add_field(name="Resources Gained", value=f"🔷 **{total_rewards['virelite']:,}** Virelite\n🌀 **{total_rewards['remna']:,}** Remna")
                
                # We need to edit the original message since we sent one for the view
                await inter.edit_original_response(embed=embed, view=None)
                log_esprit_dissolve(inter, dissolved_esprits, total_rewards)
                await self._invalidate_cache(str(inter.user.id))
                return

            # Single Dissolve
            async with get_session() as s:
                # --- RACE CONDITION FIX: Lock user and esprit rows ---
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user:
                    return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
                
                ue = await s.get(UserEsprit, esprit_id, with_for_update=True, options=[selectinload(UserEsprit.esprit_data)])
                
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Esprit not found or it does not belong to you.", ephemeral=True)
                if ue.id in {user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id}:
                    return await inter.followup.send("❌ You cannot dissolve an Esprit that is part of your active team.", ephemeral=True)
                if ue.locked:
                    return await inter.followup.send("❌ This Esprit is locked. Unlock it before dissolving.", ephemeral=True)

                confirm_view = ConfirmationView(inter.user.id)
                await inter.followup.send(
                    embed=discord.Embed(
                        title="⚠️ Confirm Dissolve",
                        description=f"Are you sure you want to dissolve **{ue.esprit_data.name}** (Lvl {ue.current_level})? This cannot be undone.",
                        color=discord.Color.orange()
                    ),
                    view=confirm_view, ephemeral=True
                )
                await confirm_view.wait()

                if not confirm_view.value:
                    await inter.edit_original_response(content="❌ Dissolve cancelled.", embed=None, view=None)
                    return

                reward = rewards_cfg.get(ue.esprit_data.rarity, {})
                virelite_gain = reward.get("virelite", 0)
                remna_gain = reward.get("remna", 0)
                
                user.virelite += virelite_gain
                user.remna += remna_gain
                
                dissolved_copy = ue # For logging
                await s.delete(ue)
                await s.commit()

            embed = discord.Embed(
                title="♻️ Dissolve Complete",
                description=f"**{dissolved_copy.esprit_data.name}** was dissolved.",
                color=discord.Color.green()
            )
            embed.add_field(name="Resources Gained", value=f"🔷 **{virelite_gain:,}** Virelite\n🌀 **{remna_gain:,}** Remna")
            await inter.edit_original_response(embed=embed, view=None)
            
            log_esprit_dissolve(inter, [dissolved_copy], {"virelite": virelite_gain, "remna": remna_gain})
            await self._invalidate_cache(str(inter.user.id))

        except Exception as e:
            await self._handle_error(inter, e)
            
    @app_commands.command(name="team_optimize", description="Automatically equip your three strongest Esprits.")
    async def team_optimize(self, inter: discord.Interaction):
        try:
            await inter.response.defer() # Public command
            if not await self._check_rl(inter): return

            combat_cfg = self.config_manager.get_config('data/config/combat_settings') or {}
            
            async with get_session() as s:
                # --- RACE CONDITION FIX: Lock user row ---
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user:
                    return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
                
                esprits = await self._get_collection(str(inter.user.id))
                if len(esprits) < 3:
                    return await inter.followup.send("❌ You need at least 3 Esprits to optimize your team.", ephemeral=True)

                power_cfg=combat_cfg.get("power_calculation", {})
                stat_cfg=combat_cfg.get("stat_calculation", {})

                # Sort by power
                esprits.sort(key=lambda e: e.calculate_power(power_cfg, stat_cfg), reverse=True)
                
                best_three = esprits[:3]
                
                user.active_esprit_id = best_three[0].id
                user.support1_esprit_id = best_three[1].id
                user.support2_esprit_id = best_three[2].id
                
                await s.commit()

                lines = []
                icons = ["👑 Leader", "⚔️ Support 1", "🛡️ Support 2"]
                total_power = 0
                for icon, ue in zip(icons, best_three):
                    power = ue.calculate_power(power_cfg, stat_cfg)
                    total_power += power
                    lines.append(f"**{icon}:** {ue.esprit_data.name} (Sigil: {power:,})")
                
                embed = discord.Embed(
                    title="✅ Team Optimized!",
                    description="Your strongest Esprits have been equipped.",
                    color=discord.Color.green()
                )
                embed.add_field(name="New Team", value="\n".join(lines), inline=False)
                embed.set_footer(text=f"Total Team Power: {total_power:,}")
                
                await inter.followup.send(embed=embed)

        except Exception as e:
            await self._handle_error(inter, e)
            
# ─── Cog Loader ──────────────────────────────────────────────────────────────

class EspritCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = EspritGroup(bot)

    async def cog_load(self):
        self.bot.tree.add_command(self.group)
        logger.info("✅ EspritCog loaded and command group added to tree.")

    async def cog_unload(self):
        self.bot.tree.remove_command(self.group.name)
        logger.info("🛑 EspritCog unloaded and command group removed from tree.")

async def setup(bot: commands.Bot):
    await bot.add_cog(EspritCog(bot))
    logger.info("✅ EspritCog setup complete.")

