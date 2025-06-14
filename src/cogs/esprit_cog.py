# src/cogs/esprit_cog.py
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Union, Set
import traceback

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData, PLAYER_LEVEL_THRESHOLDS, RARITY_LEVEL_CAPS
from src.services.limit_break_service import LimitBreakService
from src.utils.logger import get_logger
from src.utils.cache_manager import CacheManager
from src.utils.rate_limiter import RateLimiter
from enum import Enum
from src.utils import transaction_logger

# ────────────────────────────────────────────────────────────────────────────
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
                "This confirmation isn't for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def _confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        try:
            self.result = True
            self.stop()
            await interaction.response.edit_message(content="✅ Confirmed", view=None)
        except Exception as e:
            logger.error(f"Error in confirm button: {e}")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def _cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        try:
            self.result = False
            self.stop()
            await interaction.response.edit_message(content="❌ Cancelled", view=None)
        except Exception as e:
            logger.error(f"Error in cancel button: {e}")


class EnhancedCollectionView(discord.ui.View):
    """Paginated, sortable, filterable Esprit collection."""

    def __init__(
        self,
        all_esprits: List[UserEsprit],
        author_id: int,
        bot: commands.Bot,
        power_config: Dict,
        stat_config: Dict
    ):
        super().__init__(timeout=INTERACTION_TIMEOUT)
        self.all_esprits = all_esprits
        self.filtered_esprits = all_esprits
        self.author_id = author_id
        self.bot = bot
        self.power_config = power_config
        self.stat_config = stat_config
        self.current_page = 0
        self.sort_by = "name"  # name | level | rarity
        self.filter_rarity: Optional[str] = None
        self.page_size = 10

        self.update_pages()
        self.update_buttons()

    # ── helpers ────────────────────────────────────────────────────────────
    def _rarity_order(self, r: str) -> int:
        return {
            "Common": 0, "Uncommon": 1, "Rare": 2, "Epic": 3,
            "Celestial": 4, "Supreme": 5, "Deity": 6,
        }.get(r, 0)

    def _rarity_emoji(self, r: str) -> str:
        return {
            "Common": "⚪", "Uncommon": "🟢", "Rare": "🔵", "Epic": "🟣",
            "Celestial": "🟡", "Supreme": "🔴", "Deity": "🌟",
        }.get(r, "❓")

    # ── pagination ─────────────────────────────────────────────────────────
    def update_pages(self) -> None:
        try:
            self.filtered_esprits = (
                [e for e in self.all_esprits if e.esprit_data.rarity == self.filter_rarity]
                if self.filter_rarity
                else list(self.all_esprits)
            )

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
        except Exception as e:
            logger.error(f"Error updating pages: {e}")
            self.pages = [discord.Embed(title="Error", description="Failed to load collection")]

    def _build_embeds(self) -> List[discord.Embed]:
        try:
            if not self.filtered_esprits:
                return [
                    discord.Embed(
                        title="📦 Esprit Collection",
                        description="No Esprits match these filters.",
                        color=discord.Color.light_grey(),
                    )
                ]

            total_sigil = sum(self._safe_calculate_power(e) for e in self.filtered_esprits)
            pages: List[discord.Embed] = []

            for i in range(0, len(self.filtered_esprits), self.page_size):
                chunk = self.filtered_esprits[i : i + self.page_size]
                embed = discord.Embed(
                    title="📦 Esprit Collection",
                    description=(
                        f"**Total:** {len(self.filtered_esprits)} | **Sigil:** {total_sigil:,} | "
                        f"**Page:** {i//self.page_size + 1}/{(len(self.filtered_esprits)-1)//self.page_size + 1}"
                    ),
                    color=discord.Color.dark_gold(),
                )

                for ue in chunk:
                    try:
                        rarity_emoji = self._rarity_emoji(ue.esprit_data.rarity)
                        team_indicator = ""
                        if hasattr(self, "user_data") and self.user_data:
                            if ue.id == self.user_data.get("active_esprit_id"):
                                team_indicator = " 👑"
                            elif ue.id in {self.user_data.get("support1_esprit_id"), self.user_data.get("support2_esprit_id")}:
                                team_indicator = " ⚔️"

                        lb_indicator = f" 🔓{ue.limit_breaks_performed}" if hasattr(ue, 'limit_breaks_performed') and ue.limit_breaks_performed > 0 else ""
                        level_cap = self._safe_get_level_cap(ue)

                        embed.add_field(
                            name=f"{rarity_emoji} **{ue.esprit_data.name}**{team_indicator}{lb_indicator}",
                            value=(
                                f"ID: `{ue.id}` | Lvl: **{ue.current_level}/{level_cap}** | "
                                f"Sigil: **{self._safe_calculate_power(ue):,}**"
                            ),
                            inline=False,
                        )
                    except Exception as e:
                        logger.error(f"Error building embed field for esprit {ue.id}: {e}")
                        embed.add_field(name="❌ Error", value="Failed to load esprit data", inline=False)

                embed.set_footer(text=f"Sort: {self.sort_by.title()} • Filter: {self.filter_rarity or 'All'}")
                pages.append(embed)
            return pages
        except Exception as e:
            logger.error(f"Error building embeds: {e}")
            return [discord.Embed(title="Error", description="Failed to build collection view")]

    def _safe_calculate_power(self, esprit: UserEsprit) -> int:
        """Safely calculate esprit power without session dependencies"""
        try:
            # --- 3. USE THE STORED CONFIGS ---
            return esprit.calculate_power(self.power_config, self.stat_config)
        except Exception as e:
            logger.error(f"Error calculating power for esprit {esprit.id}: {e}")
            return 0

    def _safe_get_level_cap(self, esprit: UserEsprit) -> int:
        """Safely get level cap using player progression system"""
        try:
            return esprit.get_current_level_cap()
        except Exception:
            try:
                rarity_cap = RARITY_LEVEL_CAPS.get(esprit.esprit_data.rarity, 100)
                return min(20, rarity_cap)
            except Exception:
                return 20

    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("You can't control this view.", ephemeral=True)
            return False
        return True

    def update_buttons(self) -> None:
        try:
            self.first_button.disabled = self.current_page == 0
            self.previous_button.disabled = self.current_page == 0
            self.last_button.disabled = self.current_page >= len(self.pages) - 1
            self.next_button.disabled = self.current_page >= len(self.pages) - 1
        except Exception as e:
            logger.error(f"Error updating buttons: {e}")

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_button(self, inter: discord.Interaction, _: discord.ui.Button):
        try:
            self.current_page = 0
            self.update_buttons()
            await inter.response.edit_message(embed=self.pages[self.current_page], view=self)
        except Exception as e:
            logger.error(f"Error in first button: {e}")

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_button(self, inter: discord.Interaction, _: discord.ui.Button):
        try:
            self.current_page -= 1
            self.update_buttons()
            await inter.response.edit_message(embed=self.pages[self.current_page], view=self)
        except Exception as e:
            logger.error(f"Error in previous button: {e}")

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, inter: discord.Interaction, _: discord.ui.Button):
        try:
            self.current_page += 1
            self.update_buttons()
            await inter.response.edit_message(embed=self.pages[self.current_page], view=self)
        except Exception as e:
            logger.error(f"Error in next button: {e}")

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_button(self, inter: discord.Interaction, _: discord.ui.Button):
        try:
            self.current_page = len(self.pages) - 1
            self.update_buttons()
            await inter.response.edit_message(embed=self.pages[self.current_page], view=self)
        except Exception as e:
            logger.error(f"Error in last button: {e}")

    @discord.ui.select(
        placeholder="Sort by…",
        options=[
            discord.SelectOption(label="Name", value="name", emoji="📝"),
            discord.SelectOption(label="Level", value="level", emoji="📈"),
            discord.SelectOption(label="Rarity", value="rarity", emoji="💎"),
        ],
    )
    async def sort_select(self, inter: discord.Interaction, select: discord.ui.Select):
        try:
            self.sort_by = select.values[0]
            self.update_pages()
            self.update_buttons()
            await inter.response.edit_message(embed=self.pages[self.current_page], view=self)
        except Exception as e:
            logger.error(f"Error in sort select: {e}")

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
        try:
            self.filter_rarity = None if select.values[0] == "all" else select.values[0]
            self.current_page = 0
            self.update_pages()
            self.update_buttons()
            await inter.response.edit_message(embed=self.pages[self.current_page], view=self)
        except Exception as e:
            logger.error(f"Error in filter select: {e}")


class BulkDissolveView(discord.ui.View):
    """Interactive multi-dissolve selection."""
    def __init__(self, esprits: List[UserEsprit], author_id: int):
        super().__init__(timeout=300)
        self.esprits = esprits[:MAX_BULK_OPERATIONS]
        self.author_id = author_id
        self.selected_ids: Set[str] = set()
        self._refresh_options()

    def _rarity_emoji(self, r: str) -> str:
        return {"Common": "⚪", "Uncommon": "🟢", "Rare": "🔵", "Epic": "🟣", "Celestial": "🟡", "Supreme": "🔴", "Deity": "🌟"}.get(r, "❓")

    def _refresh_options(self) -> None:
        try:
            opts: List[discord.SelectOption] = []
            for e in self.esprits:
                emoji = self._rarity_emoji(e.esprit_data.rarity)
                opts.append(discord.SelectOption(label=f"{e.esprit_data.name} • Lvl {e.current_level}", value=e.id, emoji=emoji, description=f"{e.esprit_data.rarity} | ID:{e.id[:8]}"))
            self.select_menu.options = opts
            self.dissolve_button.disabled = not self.selected_ids
        except Exception as e:
            logger.error(f"Error refreshing bulk dissolve options: {e}")

    @discord.ui.select(placeholder="Select Esprits to dissolve…", min_values=0, max_values=25)
    async def select_menu(self, inter: discord.Interaction, select: discord.ui.Select):
        try:
            self.selected_ids = set(select.values)
            self.dissolve_button.disabled = not self.selected_ids
            await inter.response.edit_message(view=self)
        except Exception as e:
            logger.error(f"Error in bulk dissolve select: {e}")

    @discord.ui.button(label="Dissolve Selected", style=discord.ButtonStyle.danger, disabled=True)
    async def dissolve_button(self, inter: discord.Interaction, _: discord.ui.Button):
        try:
            if not self.selected_ids: return
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

        self.config_manager = bot.config_manager
        self.game_settings = self.config_manager.get_config('data/config/game_settings')

        self.team = app_commands.Group(name="team", description="Manage your combat team", parent=self)
        self.team.add_command(app_commands.Command(name="view", callback=self.team_view, description="View your current leader / supports."))
        self.team.add_command(app_commands.Command(name="set", callback=self.team_set, description="Assign an Esprit to a team slot."))
        self.team.add_command(app_commands.Command(name="optimize", callback=self.team_optimize, description="AI-driven recommendation."))

    async def _handle_command_error(self, inter: discord.Interaction, error: Exception):
        error_id = id(error)
        logger.error(f"Command error {error_id}: {type(error).__name__}: {error}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        try:
            if not inter.response.is_done():
                await inter.response.send_message(f"❌ An error occurred. Please try again later. (Error ID: {error_id})", ephemeral=True)
            else:
                await inter.followup.send(f"❌ An error occurred. Please try again later. (Error ID: {error_id})", ephemeral=True)
        except Exception as follow_error:
            logger.error(f"Failed to send error message: {follow_error}")

    async def _ensure_user(self, user_id: str) -> bool:
        try:
            async with get_session() as s:
                if not await s.get(User, user_id):
                    s.add(User(user_id=user_id, username="Unknown"))
                    await s.commit()
                    logger.info(f"Created new user: {user_id}")
                return True
        except SQLAlchemyError as e:
            logger.error(f"Database error in _ensure_user: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in _ensure_user: {e}")
            return False

    async def _get_collection(self, user_id: str) -> List[UserEsprit]:
        cache_key = f"user:{user_id}:collection"
        try:
            if cached := await self.cache.get(cache_key): return cached
            async with get_session() as s:
                stmt = select(UserEsprit).where(UserEsprit.owner_id == user_id).options(selectinload(UserEsprit.esprit_data))
                result = await asyncio.wait_for(s.execute(stmt), timeout=10.0)
                esprits = result.scalars().all()
                await self.cache.set(cache_key, esprits)
                return esprits
        except asyncio.TimeoutError:
            logger.error(f"Database timeout getting collection for user {user_id}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in _get_collection: {e}")
            return []

    async def _get_user_esprit(self, esprit_id: str, user_id: str) -> Optional[UserEsprit]:
        try:
            async with get_session() as s:
                stmt = select(UserEsprit).where(UserEsprit.id == esprit_id).options(selectinload(UserEsprit.esprit_data))
                esprit = (await asyncio.wait_for(s.execute(stmt), timeout=5.0)).scalar_one_or_none()
                return esprit if esprit and esprit.owner_id == user_id else None
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting esprit {esprit_id}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting esprit {esprit_id}: {e}")
            return None

    async def _invalidate(self, user_id: str) -> None:
        try:
            await self.cache.clear_pattern(f"user:{user_id}:")
        except Exception as e:
            logger.error(f"Error invalidating cache for user {user_id}: {e}")

    @app_commands.command(name="collection", description="Show your Esprits.")
    async def collection(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

            if not await self._ensure_user(str(inter.user.id)):
                await inter.followup.send("❌ User setup failed. Please try again.", ephemeral=True)
                return
            esprits = await self._get_collection(str(inter.user.id))
            if not esprits:
                return await inter.followup.send(embed=discord.Embed(title="🌱 No Esprits Yet", description="Use `/summon` to obtain your first Esprit.", color=discord.Color.blue()))
            try:
                async with get_session() as s:
                    u = await s.get(User, str(inter.user.id))
                    user_data = {"active_esprit_id": getattr(u, 'active_esprit_id', None), "support1_esprit_id": getattr(u, 'support1_esprit_id', None), "support2_esprit_id": getattr(u, 'support2_esprit_id', None)}
            except Exception as e:
                logger.error(f"Error getting user data for collection: {e}")
                user_data = {"active_esprit_id": None, "support1_esprit_id": None, "support2_esprit_id": None}
            
            power_config = self.game_settings.get("power_calculation", {})
            stat_config = self.game_settings.get("stat_calculation", {})
            
            view = EnhancedCollectionView(
                esprits, 
                inter.user.id, 
                self.bot, 
                power_config=power_config, 
                stat_config=stat_config
            )
            view.user_data = user_data
            await inter.followup.send(embed=view.pages[0], view=view)

        except Exception as e:
            await self._handle_command_error(inter, e)

    @app_commands.command(name="details", description="Full stat sheet.")
    @app_commands.describe(esprit_id="Copy ID from /esprit collection.")
    async def details(self, inter: discord.Interaction, esprit_id: str):
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)
            
            if not await self._ensure_user(str(inter.user.id)):
                await inter.followup.send("❌ User setup failed. Please try again.", ephemeral=True)
                return

            # --- NEW: Load all necessary configuration sections ---
            prog_config = self.game_settings.get("progression", {})
            stat_config = self.game_settings.get("stat_calculation", {})
            power_config = self.game_settings.get("power_calculation", {})
            lb_config = self.game_settings.get("limit_break_system", {})
            upgrade_config = self.game_settings.get("esprit_upgrade_system", {})


            async with get_session() as s:
                stmt = select(UserEsprit).where(UserEsprit.id == esprit_id).options(selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner))
                ue = (await s.execute(stmt)).scalar_one_or_none()
                
                if not ue:
                    return await inter.followup.send("❌ Esprit not found.", ephemeral=True)
                if ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Not your esprit.", ephemeral=True)

                ed = ue.esprit_data
                
                # --- UPDATED: Pass configs to model methods ---
                level_cap = ue.get_current_level_cap(prog_config)
                power = ue.calculate_power(power_config, stat_config)
                hp = ue.calculate_stat('hp', stat_config)
                attack = ue.calculate_stat('attack', stat_config)
                defense = ue.calculate_stat('defense', stat_config)
                speed = ue.calculate_stat('speed', stat_config)
                magic_resist = ue.calculate_stat('magic_resist', stat_config)

                embed = discord.Embed(title=f"{ed.name} • Lvl {ue.current_level}/{level_cap}", color=self._rarity_color(ed.rarity))
                
                embed.add_field(name="Identity", value=f"ID `{ue.id}`\n{ed.rarity} {self._rarity_emoji(ed.rarity)}", inline=True)
                embed.add_field(name="Power", value=f"**{power:,}** Sigil", inline=True)
                
                embed.add_field(
                    name="Primary Stats",
                    value=(
                        f"HP **{hp:,}**\nATK **{attack:,}**\n"
                        f"DEF **{defense:,}**\nSPD **{speed:,}**"
                    ),
                    inline=True
                )
                
                embed.add_field(
                    name="Secondary Stats",
                    value=(
                        f"MagicRes **{magic_resist:,}**\nCrit {ed.base_crit_rate:.0%}\n"
                        f"Block {ed.base_block_rate:.0%}\nDodge {ed.base_dodge_chance:.0%}"
                    ),
                    inline=True
                )

                # --- UPDATED: Pass configs to limit break methods ---
                can_break = ue.can_limit_break(prog_config)
                if ue.current_level < level_cap:
                    # Add upgrade cost info if not at cap
                    cost_formula = upgrade_config.get("cost_formula", "15 + (current_level * 8)")
                    cost = eval(cost_formula, {"current_level": ue.current_level})
                    embed.add_field(name="⚡ Next Upgrade", value=f"Cost: **{cost:,}** Virelite", inline=True)
                elif can_break["can_break"]:
                    cost = ue.get_limit_break_cost(lb_config)
                    lb_text = f"🔓 **Ready to Limit Break!**\nCost: {cost['remna']:,} Remna\n{cost['virelite']:,} Virelite"
                    embed.add_field(name="⚡ Limit Break", value=lb_text, inline=True)
                else: # At cap, but cannot limit break
                     embed.add_field(name="⚡ Limit Break", value=f"Player level too low to break further.", inline=True)

                if ue.limit_breaks_performed > 0:
                    boost_percent = ((ue.stat_boost_multiplier - 1) * 100)
                    embed.add_field(name="🔥 Limit Breaks", value=f"Performed: **{ue.limit_breaks_performed}**\nStat Boost: **+{boost_percent:.1f}%**", inline=True)

                if ed.description:
                    embed.add_field(name="Lore", value=ed.description[:200] + "…" if len(ed.description) > 200 else ed.description, inline=False)
                
                await inter.followup.send(embed=embed)
        except Exception as e:
            await self._handle_command_error(inter, e)

    @app_commands.command(name="limitbreak", description="Break through level limits to increase an Esprit's potential!")
    @app_commands.describe(esprit_id="The ID of the Esprit to limit break.")
    async def limitbreak(self, inter: discord.Interaction, esprit_id: str):
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

            # --- NEW: Load all necessary configuration sections ---
            prog_config = self.game_settings.get("progression", {})
            lb_config = self.game_settings.get("limit_break_system", {})
            stat_config = self.game_settings.get("stat_calculation", {})
            power_config = self.game_settings.get("power_calculation", {})

            if not lb_config.get("enabled", False):
                return await inter.followup.send("❌ The Limit Break system is currently disabled.", ephemeral=True)

            async with get_session() as s:
                # Get user and esprit in a single transaction
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                stmt = select(UserEsprit).where(UserEsprit.id == esprit_id).options(selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner))
                esprit = (await s.execute(stmt)).scalar_one_or_none()
            
                if not user:
                    return await inter.followup.send("❌ User not found!", ephemeral=True)
                if not esprit or esprit.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Esprit not found or not yours!", ephemeral=True)

                # --- UPDATED: Pass config to model methods ---
                can_break = esprit.can_limit_break(prog_config)
                current_cap = esprit.get_current_level_cap(prog_config)

                if not can_break["can_break"]:
                    reason = can_break.get("reason")
                    if reason == "not_at_cap":
                        return await inter.followup.send(f"❌ {esprit.esprit_data.name} must be at level {current_cap} to limit break! (Current: {esprit.current_level})")
                    elif reason == "at_rarity_maximum":
                        return await inter.followup.send(f"❌ {esprit.esprit_data.name} is at the absolute maximum level for a {esprit.esprit_data.rarity} Esprit!")
                    elif reason == "insufficient_player_level":
                        return await inter.followup.send(f"❌ Your player level is too low! Level up your character to unlock higher Esprit caps.")
                    else:
                        return await inter.followup.send("❌ This Esprit cannot be limit broken at this time.")

                # Get costs using the config
                cost = esprit.get_limit_break_cost(lb_config)

                # Check resources
                if user.remna < cost["remna"]:
                    return await inter.followup.send(f"❌ Need **{cost['remna']:,}** Remna (You have {user.remna:,})")
                if user.virelite < cost["virelite"]:
                    return await inter.followup.send(f"❌ Need **{cost['virelite']:,}** Virelite (You have {user.virelite:,})")

                # --- Perform limit break ---
                old_power = esprit.calculate_power(power_config, stat_config)
                
                # Deduct costs from the user
                user.remna -= cost["remna"]
                user.virelite -= cost["virelite"]

                # Apply limit break using the multiplier from config
                compound_rate = lb_config.get("compound_rate", 1.1)
                esprit.stat_boost_multiplier *= compound_rate
                esprit.limit_breaks_performed += 1
                esprit.current_hp = esprit.calculate_stat('hp', stat_config)  # Heal to new max

                # Recalculate new power and level cap with the same configs
                new_power = esprit.calculate_power(power_config, stat_config)
                new_cap = esprit.get_current_level_cap(prog_config)
                
                await s.commit()

                # --- Success Embed ---
                embed = discord.Embed(
                    title="🔓 LIMIT BREAK SUCCESSFUL!",
                    description=f"**{esprit.esprit_data.name}** has transcended its limits!",
                    color=discord.Color.gold()
                )
                embed.add_field(name="💪 Power Increase", value=f"{old_power:,} → **{new_power:,}** Sigil", inline=True)
                embed.add_field(name="📈 New Level Cap", value=f"Can now reach level **{new_cap}**", inline=True)
                embed.add_field(name="💰 Cost Paid", value=f"{cost['remna']:,} Remna\n{cost['virelite']:,} Virelite", inline=True)
                embed.add_field(
                    name="🔥 Total Limit Breaks",
                    value=f"**{esprit.limit_breaks_performed}** performed\nStat Multiplier: **{esprit.stat_boost_multiplier:.2f}x**",
                    inline=True
                )

                transaction_logger.log_limit_break(inter, esprit, cost)

                await self._invalidate(str(inter.user.id))
                await inter.followup.send(embed=embed)

        except Exception as e:
            await self._handle_command_error(inter, e)
            
    # ────────────────────────────────────────────────────────────────────
    # upgrade (REVISED AND FIXED)
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="upgrade", description="Spend Virelite to level up an Esprit.")
    @app_commands.describe(
        esprit_id="The ID of the Esprit you want to upgrade.",
        levels="The number of levels to add (1-10, or 'max').",
    )
    async def upgrade(self, inter: discord.Interaction, esprit_id: str, levels: str):
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

            # --- NEW: Load all necessary configuration sections ---
            prog_config = self.game_settings.get("progression", {})
            upgrade_config = self.game_settings.get("esprit_upgrade_system", {})
            stat_config = self.game_settings.get("stat_calculation", {})
            power_config = self.game_settings.get("power_calculation", {})

            if not upgrade_config.get("enabled", True):
                return await inter.followup.send("❌ The Esprit upgrade system is currently disabled by the administrator.", ephemeral=True)

            async with get_session() as s:
                # Get the user and the Esprit they own in a single, safe transaction
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                ue = await s.get(
                    UserEsprit,
                    esprit_id,
                    with_for_update=True,
                    options=[selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner)]
                )

                if not user:
                    return await inter.followup.send("❌ Could not find your user profile.", ephemeral=True)
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Esprit not found or it's not yours.", ephemeral=True)

                # --- UPDATED: Pass progression config to the level cap check ---
                current_level_cap = ue.get_current_level_cap(prog_config)
                if ue.current_level >= current_level_cap:
                    return await inter.followup.send(
                        f"❌ **{ue.esprit_data.name}** is at its current level cap ({current_level_cap}).\n"
                        f"Use `/esprit limitbreak` to raise the cap.",
                        ephemeral=True
                    )

                # Determine the number of levels to add, handling the 'max' keyword
                max_possible_levels = current_level_cap - ue.current_level
                levels_to_add = 0
                if levels.lower() == 'max':
                    levels_to_add = max_possible_levels
                else:
                    try:
                        num_levels = int(levels)
                        if not (1 <= num_levels <= 10):
                            return await inter.followup.send("Levels must be a number between 1 and 10, or 'max'.", ephemeral=True)
                        levels_to_add = min(num_levels, max_possible_levels)
                    except ValueError:
                        return await inter.followup.send("Invalid input for levels. Use a number (1-10) or 'max'.", ephemeral=True)

                if levels_to_add <= 0:
                    return await inter.followup.send(f"❌ Cannot level up. Already at cap ({current_level_cap}).", ephemeral=True)

                # --- NEW: Use the cost formula from the config file ---
                cost_formula = upgrade_config.get("cost_formula", "15 + (current_level * 8)")
                total_virelite_cost = sum(eval(cost_formula, {"current_level": lvl}) for lvl in range(ue.current_level, ue.current_level + levels_to_add))

                if user.virelite < total_virelite_cost:
                    return await inter.followup.send(
                        f"❌ You need **{total_virelite_cost:,}** Virelite, but you only have **{user.virelite:,}**.",
                        ephemeral=True
                    )

                # Store old stats for the results embed
                old_level = ue.current_level
                old_power = ue.calculate_power(power_config, stat_config)
                
                # Apply the upgrade
                user.virelite -= total_virelite_cost
                ue.current_level += levels_to_add
                ue.current_hp = ue.calculate_stat('hp', stat_config) # Heal to new max HP

                # Calculate new power for the results embed
                new_power = ue.calculate_power(power_config, stat_config)
                
                await s.commit()
                await self._invalidate(str(inter.user.id))

                transaction_logger.log_esprit_upgrade(inter, ue, old_level, total_virelite_cost)

                # Create and send the success message
                embed = discord.Embed(
                    title="⭐ Upgrade Complete!",
                    description=f"**{ue.esprit_data.name}** is now Level **{ue.current_level}**!",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Levels Gained", value=f"`+{levels_to_add}`")
                embed.add_field(name="Virelite Spent", value=f"`{total_virelite_cost:,}`")
                embed.add_field(name="Power Increase", value=f"{old_power:,} → **{new_power:,}** (`+{new_power - old_power:,}`)")
                await inter.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await self._handle_command_error(inter, e)

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
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

            # --- NEW: Load dissolve rewards config ---
            dissolve_rewards_config = self.game_settings.get("dissolve_rewards", {})

            if multi:
                # --- Bulk Dissolve Logic ---
                valid_rarities = {"Common", "Uncommon", "Rare", "Epic", "Celestial", "Supreme", "Deity"}
                if rarity_filter and rarity_filter not in valid_rarities:
                    return await inter.followup.send("Invalid rarity filter.", ephemeral=True)

                async with get_session() as s:
                    user = await s.get(User, str(inter.user.id))
                    protected = {
                        getattr(user, 'active_esprit_id', None),
                        getattr(user, 'support1_esprit_id', None),
                        getattr(user, 'support2_esprit_id', None),
                    }
                    protected.discard(None)

                    stmt = select(UserEsprit).where(and_(
                        UserEsprit.owner_id == str(inter.user.id),
                        ~UserEsprit.id.in_(protected) if protected else True,
                    )).options(selectinload(UserEsprit.esprit_data))

                    if rarity_filter:
                        stmt = stmt.where(UserEsprit.esprit_data.has(rarity=rarity_filter))
                    
                    esprits = (await s.execute(stmt)).scalars().all()

                if not esprits:
                    return await inter.followup.send("No Esprits found to dissolve with the specified filters.", ephemeral=True)

                view = BulkDissolveView(esprits, inter.user.id)
                await inter.followup.send(
                    embed=discord.Embed(
                        title="♻️ Bulk Dissolve",
                        description="Select up to 10 Esprits to dissolve. Team members are protected.",
                        color=discord.Color.orange(),
                    ),
                    view=view,
                )
                await view.wait()
                if not view.selected_ids:
                    return # User cancelled or selected nothing

                # --- UPDATED: Pass config to the processing helper ---
                await self._process_bulk_dissolve(inter, view.selected_ids, dissolve_rewards_config)
                return

            # --- Single Dissolve Logic ---
            if not esprit_id:
                return await inter.followup.send("You must provide an `esprit_id` or use `multi=True`.", ephemeral=True)

            async with get_session() as s:
                stmt = select(UserEsprit).where(UserEsprit.id == esprit_id).options(selectinload(UserEsprit.esprit_data))
                ue = (await s.execute(stmt)).scalar_one_or_none()

                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Esprit not found or not yours.", ephemeral=True)

                user = await s.get(User, str(inter.user.id))
                if esprit_id in {getattr(user, 'active_esprit_id', None), getattr(user, 'support1_esprit_id', None), getattr(user, 'support2_esprit_id', None)}:
                    return await inter.followup.send("❌ You cannot dissolve an Esprit that is part of your team.", ephemeral=True)

                confirm = ConfirmationView(inter.user.id)
                await inter.followup.send(
                    embed=discord.Embed(
                        title="⚠️ Confirm Dissolve",
                        description=f"Are you sure you want to dissolve **{ue.esprit_data.name}** (Lvl {ue.current_level})?",
                        color=discord.Color.orange(),
                    ),
                    view=confirm,
                )
                await confirm.wait()
                if not confirm.result:
                    return

                # --- UPDATED: Pass config to the reward calculator ---
                rewards = self._calc_rewards([ue], dissolve_rewards_config)
                user.virelite += rewards["virelite"]
                user.remna += rewards["remna"]

                await s.delete(ue)
                s.add(user)
                await s.commit()

                transaction_logger.log_esprit_dissolve(inter, [ue], rewards)

                await self._invalidate(str(inter.user.id))

                await inter.followup.send(
                    embed=discord.Embed(
                        title="♻️ Dissolved Successfully",
                        description="You received:\n" + "\n".join(f"**{v:,}** {k.title()}" for k, v in rewards.items()),
                        color=discord.Color.green(),
                    ),
                    ephemeral=True,
                )

        except Exception as e:
            await self._handle_command_error(inter, e)

    async def _process_bulk_dissolve(self, inter: discord.Interaction, ids: Set[str], rewards_config: Dict):
        try:
            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user:
                    # This check is unlikely to fail but is good practice
                    return await inter.followup.send("Could not find your user profile.", ephemeral=True)

                stmt = select(UserEsprit).where(UserEsprit.id.in_(ids)).options(selectinload(UserEsprit.esprit_data))
                esprits_to_dissolve = (await s.execute(stmt)).scalars().all()

                if len(esprits_to_dissolve) != len(ids) or any(e.owner_id != str(inter.user.id) for e in esprits_to_dissolve):
                    return await inter.followup.send("An ownership mismatch occurred. Please try again.", ephemeral=True)

                # --- UPDATED: Pass config to the reward calculator ---
                rewards = self._calc_rewards(esprits_to_dissolve, rewards_config)
                user.virelite += rewards["virelite"]
                user.remna += rewards["remna"]

                for e in esprits_to_dissolve:
                    await s.delete(e)
                
                s.add(user)
                await s.commit()

            transaction_logger.log_esprit_dissolve(inter, esprits_to_dissolve, rewards)

            await self._invalidate(str(inter.user.id))
            await inter.followup.send(
                embed=discord.Embed(
                    title="♻️ Bulk Dissolve Complete",
                    description=(
                        f"Dissolved **{len(esprits_to_dissolve)}** Esprit(s).\n\n**Total Rewards:**\n"
                        + "\n".join(f"**{v:,}** {k.title()}" for k, v in rewards.items())
                    ),
                    color=discord.Color.green(),
                ),
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error in bulk dissolve processing: {e}")
            await inter.followup.send("❌ An error occurred while processing the bulk dissolve.", ephemeral=True)

    # --- UPDATED: Reward calculator now requires the config ---
    def _calc_rewards(self, esprits: List[UserEsprit], rewards_config: Dict) -> Dict[str, int]:
        totals = {"virelite": 0, "remna": 0}
        for e in esprits:
            # Use the passed-in config dictionary
            rarity_rewards = rewards_config.get(e.esprit_data.rarity, {"virelite": 0, "remna": 0})
            totals["virelite"] += rarity_rewards.get("virelite", 0)
            totals["remna"] += rarity_rewards.get("remna", 0)
        return totals

    @app_commands.command(name="search", description="Find your owned Esprits by name.")
    async def search(self, inter: discord.Interaction, query: str):
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

            # --- NEW: Load necessary configuration sections ---
            prog_config = self.game_settings.get("progression", {})
            stat_config = self.game_settings.get("stat_calculation", {})
            power_config = self.game_settings.get("power_calculation", {})

            # Get the user's full collection to search through it
            esprits = await self._get_collection(str(inter.user.id))
            
            # Filter the collection based on the search query
            hits = [
                e
                for e in esprits
                if query.lower() in e.esprit_data.name.lower()
            ][:25] # Limit to 25 results for performance

            if not hits:
                return await inter.followup.send("No Esprits found matching that query.", ephemeral=True)

            lines = []
            for e in hits:
                try:
                    # --- UPDATED: Pass configs to model methods ---
                    level_cap = e.get_current_level_cap(prog_config)
                    power = e.calculate_power(power_config, stat_config)
                    lines.append(
                        f"`{e.id}` • {e.esprit_data.name} • "
                        f"Lvl {e.current_level}/{level_cap} • Sigil {power:,}"
                    )
                except Exception as ex:
                    logger.error(f"Error formatting search result for {e.id}: {ex}")
                    lines.append(f"`{e.id}` • {e.esprit_data.name} • Error loading data")

            await inter.followup.send(
                embed=discord.Embed(
                    title=f"🔍 Search Results ({len(hits)})", description="\n".join(lines)
                ),
                ephemeral=True,
            )
        except Exception as e:
            await self._handle_command_error(inter, e)

    @app_commands.command(
        name="compare", description="Compare two of your Esprits' stats and Sigil."
    )
    @app_commands.describe(
        esprit_a="The ID of the first Esprit.",
        esprit_b="The ID of the second Esprit."
    )
    async def compare(
        self, inter: discord.Interaction, esprit_a: str, esprit_b: str
    ):
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

            if esprit_a == esprit_b:
                return await inter.followup.send("❌ You must provide two different Esprit IDs to compare.", ephemeral=True)

            # --- NEW: Load all necessary configuration sections ---
            prog_config = self.game_settings.get("progression", {})
            stat_config = self.game_settings.get("stat_calculation", {})
            power_config = self.game_settings.get("power_calculation", {})

            async with get_session() as s:
                stmt = (
                    select(UserEsprit)
                    .where(UserEsprit.id.in_([esprit_a, esprit_b]))
                    .options(selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner))
                )
                rows = (await s.execute(stmt)).scalars().all()

            # Verify that both esprits were found and belong to the user
            if len(rows) != 2 or any(r.owner_id != str(inter.user.id) for r in rows):
                return await inter.followup.send("❌ One or both Esprit IDs are invalid or do not belong to you.", ephemeral=True)

            # Map the results to their IDs to ensure correct order
            esprits_map = {r.id: r for r in rows}
            a = esprits_map.get(esprit_a)
            b = esprits_map.get(esprit_b)

            embed = discord.Embed(title="⚖️ Esprit Comparison", color=discord.Color.dark_teal())
            
            for ue in [a, b]:
                try:
                    ed = ue.esprit_data
                    # --- UPDATED: Pass configs to model methods ---
                    level_cap = ue.get_current_level_cap(prog_config)
                    power = ue.calculate_power(power_config, stat_config)
                    
                    lb_info = f" (🔓{ue.limit_breaks_performed})" if ue.limit_breaks_performed > 0 else ""
                    
                    embed.add_field(
                        name=f"{self._rarity_emoji(ed.rarity)} {ed.name}",
                        value=(
                            f"**Sigil:** `{power:,}`\n"
                            f"**Level:** `{ue.current_level}/{level_cap}`{lb_info}"
                        ),
                        inline=False,
                    )
                except Exception as ex:
                    logger.error(f"Error comparing esprit {ue.id}: {ex}")
                    embed.add_field(
                        name="Error",
                        value=f"Failed to load data for Esprit ID `{ue.id}`",
                        inline=False,
                    )
            
            await inter.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await self._handle_command_error(inter, e)

    async def team_view(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

            # --- NEW: Load necessary configuration sections ---
            stat_config = self.game_settings.get("stat_calculation", {})
            power_config = self.game_settings.get("power_calculation", {})

            async with get_session() as s:
                user = await s.get(User, str(inter.user.id))
                if not user:
                    # This is unlikely if they can run the command, but good practice
                    return await inter.followup.send("❌ Could not find your user profile.", ephemeral=True)

                team_ids = [
                    getattr(user, 'active_esprit_id', None),
                    getattr(user, 'support1_esprit_id', None),
                    getattr(user, 'support2_esprit_id', None),
                ]
                
                # Filter out any empty slots
                valid_ids = [id for id in team_ids if id is not None]
                
                if valid_ids:
                    stmt = (
                        select(UserEsprit)
                        .where(UserEsprit.id.in_(valid_ids))
                        .options(selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner))
                    )
                    # Create a dictionary mapping Esprit ID to the Esprit object for easy lookup
                    esprits_map = {e.id: e for e in (await s.execute(stmt)).scalars().all()}
                else:
                    esprits_map = {}

            # --- Build the Display ---
            embed = discord.Embed(title="🛡️ Your Combat Team", color=discord.Color.dark_green())
            team_labels = ["Leader", "Support 1", "Support 2"]
            total_team_power = 0

            for label, esprit_id in zip(team_labels, team_ids):
                if not esprit_id or esprit_id not in esprits_map:
                    embed.add_field(name=f"**{label}**", value="— *Empty Slot* —", inline=False)
                else:
                    e = esprits_map[esprit_id]
                    try:
                        # --- UPDATED: Pass configs to the power calculation ---
                        power = e.calculate_power(power_config, stat_config)
                        total_team_power += power
                        
                        embed.add_field(
                            name=f"**{label}:** {self._rarity_emoji(e.esprit_data.rarity)} {e.esprit_data.name}",
                            value=f"Lvl: `{e.current_level}` | Sigil: `{power:,}`",
                            inline=False
                        )
                    except Exception as ex:
                        logger.error(f"Error displaying team esprit {esprit_id}: {ex}")
                        embed.add_field(
                            name=f"**{label}:** {e.esprit_data.name}",
                            value="Error loading stats.",
                            inline=False
                        )
            
            embed.set_footer(text=f"Total Team Sigil: {total_team_power:,}")
            await inter.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await self._handle_command_error(inter, e)

    async def team_set(self, inter: discord.Interaction, slot: TeamSlot, esprit_id: str):
        try:
            if slot not in {TeamSlot.leader, TeamSlot.support1, TeamSlot.support2}:
                return await inter.response.send_message("Invalid slot.", ephemeral=True)
            
            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)
            
            await inter.response.defer(ephemeral=True)
            async with get_session() as s:
                ue = await s.get(UserEsprit, esprit_id)
                if not ue or ue.owner_id != str(inter.user.id): return await inter.followup.send("Bad ID / not yours.", ephemeral=True)
                user = await s.get(User, str(inter.user.id))
                if slot == TeamSlot.leader: user.active_esprit_id = esprit_id
                elif slot == TeamSlot.support1: user.support1_esprit_id = esprit_id
                else: user.support2_esprit_id = esprit_id
                await s.commit()
            await self._invalidate(str(inter.user.id))
            await inter.followup.send("✅ Team updated.", ephemeral=True)
        except Exception as e:
            await self._handle_command_error(inter, e)

    async def team_optimize(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)

            if not await self.rate_limiter.check(str(inter.user.id)):
                wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
                return await inter.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

            # --- NEW: Load necessary configuration sections ---
            stat_config = self.game_settings.get("stat_calculation", {})
            power_config = self.game_settings.get("power_calculation", {})

            esprits = await self._get_collection(str(inter.user.id))
            
            if len(esprits) < 3:
                return await inter.followup.send("❌ You need at least 3 Esprits to use team optimize.", ephemeral=True)

            # --- UPDATED: Safe power calculation now uses configs ---
            def safe_power(e: UserEsprit):
                try:
                    # Pass the loaded configs to the real calculation method
                    return e.calculate_power(power_config, stat_config)
                except Exception as ex:
                    logger.error(f"Error calculating power for Esprit {e.id} during optimization: {ex}")
                    return 0
            
            # Sort all esprits by their correctly calculated power
            best_esprits = sorted(esprits, key=safe_power, reverse=True)[:3]
            
            async with get_session() as s:
                user = await s.get(User, str(inter.user.id))
                if not user:
                    return await inter.followup.send("❌ Could not find your user profile to update the team.", ephemeral=True)

                # Assign the top 3 to the user's team slots
                user.active_esprit_id = best_esprits[0].id
                user.support1_esprit_id = best_esprits[1].id
                user.support2_esprit_id = best_esprits[2].id
                
                await s.commit()

            await self._invalidate(str(inter.user.id))

            # Create a confirmation message showing the new team
            optimized_team_names = "\n".join([
                f"👑 **Leader:** {best_esprits[0].esprit_data.name} (Sigil: `{safe_power(best_esprits[0]):,}`)",
                f"⚔️ **Support 1:** {best_esprits[1].esprit_data.name} (Sigil: `{safe_power(best_esprits[1]):,}`)",
                f"⚔️ **Support 2:** {best_esprits[2].esprit_data.name} (Sigil: `{safe_power(best_esprits[2]):,}`)"
            ])

            embed = discord.Embed(
                title="✅ Team Optimized!",
                description=f"Your team has been set to the highest Sigil combination:\n\n{optimized_team_names}",
                color=discord.Color.green()
            )
            await inter.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await self._handle_command_error(inter, e)

    def _rarity_color(self, rarity: str) -> discord.Color:
        return {
            "Common": discord.Color.light_grey(), "Uncommon": discord.Color.green(), "Rare": discord.Color.blue(),
            "Epic": discord.Color.purple(), "Celestial": discord.Color.gold(), "Supreme": discord.Color.red(),
            "Deity": discord.Color.from_rgb(255, 20, 147)
        }.get(rarity, discord.Color.default())

    def _rarity_emoji(self, rarity: str) -> str:
        return {"Common": "⚪", "Uncommon": "🟢", "Rare": "🔵", "Epic": "🟣", "Celestial": "🟡", "Supreme": "🔴", "Deity": "🌟"}.get(rarity, "❓")

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
