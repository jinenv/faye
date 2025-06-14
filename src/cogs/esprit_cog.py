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
        try:
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
                        f"**Total:** {len(self.filtered_esprits)}"
                        f" | **Sigil:** {total_sigil:,}"
                        f" | **Page:** {i//self.page_size + 1}/"
                        f"{(len(self.filtered_esprits)-1)//self.page_size + 1}"
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
                            elif ue.id in {
                                self.user_data.get("support1_esprit_id"),
                                self.user_data.get("support2_esprit_id"),
                            }:
                                team_indicator = " ⚔️"

                        # Show limit break status
                        lb_indicator = ""
                        if hasattr(ue, 'limit_breaks_performed') and ue.limit_breaks_performed > 0:
                            lb_indicator = f" 🔓{ue.limit_breaks_performed}"

                        # Safe level cap calculation
                        level_cap = self._safe_get_level_cap(ue)

                        embed.add_field(
                            name=f"{rarity_emoji} **{ue.esprit_data.name}**{team_indicator}{lb_indicator}",
                            value=(
                                f"ID: `{ue.id}`"
                                f" | Lvl: **{ue.current_level}/{level_cap}**"
                                f" | Sigil: **{self._safe_calculate_power(ue):,}**"
                            ),
                            inline=False,
                        )
                    except Exception as e:
                        logger.error(f"Error building embed field for esprit {ue.id}: {e}")
                        embed.add_field(
                            name="❌ Error",
                            value=f"Failed to load esprit data",
                            inline=False,
                        )

                embed.set_footer(
                    text=f"Sort: {self.sort_by.title()} • "
                    f"Filter: {self.filter_rarity or 'All'}"
                )
                pages.append(embed)

            return pages
        except Exception as e:
            logger.error(f"Error building embeds: {e}")
            return [discord.Embed(title="Error", description="Failed to build collection view")]

    def _safe_calculate_power(self, esprit: UserEsprit) -> int:
        """Safely calculate esprit power without session dependencies"""
        try:
            # Manual calculation to avoid session issues
            ed = esprit.esprit_data
            if not ed:
                return 0
                
            # Level scaling: +5% per level
            level_multiplier = 1 + (esprit.current_level - 1) * 0.05
            
            # Limit break multiplier
            lb_multiplier = getattr(esprit, 'stat_boost_multiplier', 1.0)
            
            # Calculate weighted power
            hp = int(ed.base_hp * level_multiplier * lb_multiplier)
            attack = int(ed.base_attack * level_multiplier * lb_multiplier)
            defense = int(ed.base_defense * level_multiplier * lb_multiplier)
            speed = int(ed.base_speed * level_multiplier * lb_multiplier)
            magic_resist = int(getattr(ed, 'base_magic_resist', 0) * level_multiplier * lb_multiplier)
            
            power = (
                (hp / 4) +
                (attack * 2.5) +
                (defense * 2.5) +
                (speed * 3.0) +
                (magic_resist * 2.0) +
                (getattr(ed, 'base_crit_rate', 0) * 500) +
                (getattr(ed, 'base_block_rate', 0) * 500) +
                (getattr(ed, 'base_dodge_chance', 0) * 600) +
                (getattr(ed, 'base_mana', 0) * 0.5) +
                (getattr(ed, 'base_mana_regen', 0) * 100)
            )
            
            # Rarity multipliers
            rarity_multipliers = {
                "Common": 1.0, "Uncommon": 1.1, "Rare": 1.25, "Epic": 1.4,
                "Celestial": 1.6, "Supreme": 1.8, "Deity": 2.0
            }
            
            rarity_mult = rarity_multipliers.get(ed.rarity, 1.0)
            return max(1, int(power * rarity_mult))
            
        except Exception as e:
            logger.error(f"Error calculating power for esprit {esprit.id}: {e}")
            return 0

    def _safe_get_level_cap(self, esprit: UserEsprit) -> int:
        """Safely get level cap using player progression system"""
        try:
            # Try the model method first
            return esprit.get_current_level_cap()
        except Exception:
            try:
                # Fallback: assume player level 1 (cap 20) if no owner access
                rarity_cap = RARITY_LEVEL_CAPS.get(esprit.esprit_data.rarity, 100)
                return min(20, rarity_cap)  # Default to level 20 cap for safety
            except Exception:
                return 20

    # ── discord.ui plumbing ────────────────────────────────────────────────
    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message(
                "You can't control this view.", ephemeral=True
            )
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

    # ── nav buttons ────────────────────────────────────────────────────────
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
        try:
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
        except Exception as e:
            logger.error(f"Error refreshing bulk dissolve options: {e}")

    # ── ui elements ────────────────────────────────────────────────────────
    @discord.ui.select(
        placeholder="Select Esprits to dissolve…",
        min_values=0,
        max_values=25,
    )
    async def select_menu(self, inter: discord.Interaction, select: discord.ui.Select):
        try:
            self.selected_ids = set(select.values)
            self.dissolve_button.disabled = not self.selected_ids
            await inter.response.edit_message(view=self)
        except Exception as e:
            logger.error(f"Error in bulk dissolve select: {e}")

    @discord.ui.button(
        label="Dissolve Selected", style=discord.ButtonStyle.danger, disabled=True
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

    # ── Enhanced Error Handling ────────────────────────────────────────────
    async def _handle_command_error(self, inter: discord.Interaction, error: Exception):
        """Centralized error handling for all commands"""
        error_id = id(error)
        logger.error(f"Command error {error_id}: {type(error).__name__}: {error}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        try:
            if not inter.response.is_done():
                await inter.response.send_message(
                    f"❌ An error occurred. Please try again later. (Error ID: {error_id})",
                    ephemeral=True
                )
            else:
                await inter.followup.send(
                    f"❌ An error occurred. Please try again later. (Error ID: {error_id})",
                    ephemeral=True
                )
        except Exception as follow_error:
            logger.error(f"Failed to send error message: {follow_error}")

    # ── misc helpers ───────────────────────────────────────────────────────
    async def _ensure_user(self, user_id: str) -> bool:
        """Ensure user exists, return success status"""
        try:
            async with get_session() as s:
                existing_user = await s.get(User, user_id)
                if not existing_user:
                    new_user = User(user_id=user_id, username="Unknown")
                    s.add(new_user)
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
        """Get user's esprit collection with proper error handling"""
        cache_key = f"user:{user_id}:collection"
        
        try:
            # Try cache first
            cached = await self.cache.get(cache_key)
            if cached:
                return cached

            # Database query with timeout protection
            async with get_session() as s:
                stmt = (
                    select(UserEsprit)
                    .where(UserEsprit.owner_id == user_id)
                    .options(selectinload(UserEsprit.esprit_data))
                )
                
                # Add timeout to prevent hanging
                result = await asyncio.wait_for(
                    s.execute(stmt), 
                    timeout=10.0  # 10 second timeout
                )
                
                esprits = result.scalars().all()
                await self.cache.set(cache_key, esprits)
                return esprits
                
        except asyncio.TimeoutError:
            logger.error(f"Database timeout getting collection for user {user_id}")
            return []
        except SQLAlchemyError as e:
            logger.error(f"Database error in _get_collection: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in _get_collection: {e}")
            return []

    async def _get_user_esprit(self, esprit_id: str, user_id: str) -> Optional[UserEsprit]:
        """Get a specific esprit with proper error handling"""
        try:
            async with get_session() as s:
                stmt = (
                    select(UserEsprit)
                    .where(UserEsprit.id == esprit_id)
                    .options(selectinload(UserEsprit.esprit_data))
                )
                
                result = await asyncio.wait_for(
                    s.execute(stmt),
                    timeout=5.0
                )
                
                esprit = result.scalar_one_or_none()
                
                if not esprit:
                    return None
                    
                if esprit.owner_id != user_id:
                    return None
                    
                return esprit
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting esprit {esprit_id}")
            return None
        except SQLAlchemyError as e:
            logger.error(f"Database error getting esprit {esprit_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting esprit {esprit_id}: {e}")
            return None

    async def _invalidate(self, user_id: str) -> None:
        try:
            await self.cache.clear_pattern(f"user:{user_id}:")
        except Exception as e:
            logger.error(f"Error invalidating cache for user {user_id}: {e}")

    # ────────────────────────────────────────────────────────────────────
    # collection
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="collection", description="Show your Esprits.")
    async def collection(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)
            
            if not await self._ensure_user(str(inter.user.id)):
                await inter.followup.send("❌ User setup failed. Please try again.", ephemeral=True)
                return
                
            esprits = await self._get_collection(str(inter.user.id))

            if not esprits:
                return await inter.followup.send(
                    embed=discord.Embed(
                        title="🌱 No Esprits Yet",
                        description="Use `/summon` to obtain your first Esprit.",
                        color=discord.Color.blue(),
                    )
                )

            # Get user data safely
            try:
                async with get_session() as s:
                    u = await s.get(User, str(inter.user.id))
                    user_data = {
                        "active_esprit_id": getattr(u, 'active_esprit_id', None),
                        "support1_esprit_id": getattr(u, 'support1_esprit_id', None),
                        "support2_esprit_id": getattr(u, 'support2_esprit_id', None),
                    }
            except Exception as e:
                logger.error(f"Error getting user data for collection: {e}")
                user_data = {
                    "active_esprit_id": None,
                    "support1_esprit_id": None,
                    "support2_esprit_id": None,
                }

            view = EnhancedCollectionView(esprits, inter.user.id, self.bot)
            view.user_data = user_data
            await inter.followup.send(embed=view.pages[0], view=view)
            
        except Exception as e:
            await self._handle_command_error(inter, e)

    # ────────────────────────────────────────────────────────────────────
    # details
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="details", description="Full stat sheet.")
    @app_commands.describe(esprit_id="Copy ID from /esprit collection.")
    async def details(self, inter: discord.Interaction, esprit_id: str):
        try:
            await inter.response.defer(ephemeral=True)
            
            if not await self._ensure_user(str(inter.user.id)):
                await inter.followup.send("❌ User setup failed. Please try again.", ephemeral=True)
                return

            # Keep everything in session context
            async with get_session() as s:
                stmt = (
                    select(UserEsprit)
                    .where(UserEsprit.id == esprit_id)
                    .options(
                        selectinload(UserEsprit.esprit_data),
                        selectinload(UserEsprit.owner)
                    )
                )
                
                ue = (await s.execute(stmt)).scalar_one_or_none()
                
                if not ue:
                    return await inter.followup.send("❌ Esprit not found.", ephemeral=True)
                    
                if ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Not your esprit.", ephemeral=True)

                # Calculate everything in session
                ed = ue.esprit_data
                rarity_cap = RARITY_LEVEL_CAPS.get(ed.rarity, 100)
                level_cap = ue.get_current_level_cap()

                embed = discord.Embed(
                    title=f"{ed.name} • Lvl {ue.current_level}/{level_cap}",
                    color=self._rarity_color(ed.rarity),
                )

                embed.add_field(
                    name="Identity",
                    value=f"ID `{ue.id}`\n{ed.rarity} {self._rarity_emoji(ed.rarity)}",
                    inline=True,
                )

                # Calculate stats in session
                hp = ue.calculate_stat('hp')
                attack = ue.calculate_stat('attack')
                defense = ue.calculate_stat('defense')
                speed = ue.calculate_stat('speed')
                magic_resist = ue.calculate_stat('magic_resist')
                power = ue.calculate_power()

                embed.add_field(
                    name="Primary Stats",
                    value=(
                        f"HP **{hp:,}**\n"
                        f"ATK **{attack:,}**\n"
                        f"DEF **{defense:,}**\n"
                        f"SPD **{speed:,}**"
                    ),
                    inline=True,
                )

                embed.add_field(
                    name="Secondary Stats",
                    value=(
                        f"MagicRes **{magic_resist:,}**\n"
                        f"Crit {ed.base_crit_rate:.0%}\n"
                        f"Block {ed.base_block_rate:.0%}\n"
                        f"Dodge {ed.base_dodge_chance:.0%}"
                    ),
                    inline=True,
                )

                embed.add_field(
                    name="Power",
                    value=f"**{power:,}** Sigil",
                    inline=True,
                )

                # Limit break info
                can_break = ue.can_limit_break()
                if can_break["can_break"]:
                    cost = ue.get_limit_break_cost()
                    lb_text = (
                        f"🔓 **Ready to Limit Break!**\n"
                        f"Cost: {cost['essence']:,} Essence\n"
                        f"{cost['moonglow']:,} Moonglow"
                    )
                    embed.add_field(name="⚡ Limit Break", value=lb_text, inline=True)
                elif can_break["reason"] == "not_at_cap":
                    embed.add_field(
                        name="⚡ Limit Break", 
                        value=f"Reach level {level_cap} first", 
                        inline=True
                    )

                # Limit break history
                if ue.limit_breaks_performed > 0:
                    boost_percent = ((ue.stat_boost_multiplier - 1) * 100)
                    embed.add_field(
                        name="🔥 Limit Breaks", 
                        value=f"Performed: **{ue.limit_breaks_performed}**\nStat Boost: **+{boost_percent:.1f}%**", 
                        inline=True
                    )

                if ed.description:
                    description = ed.description[:200] + "…" if len(ed.description) > 200 else ed.description
                    embed.add_field(name="Lore", value=description, inline=False)

                await inter.followup.send(embed=embed)
                    
        except Exception as e:
            await self._handle_command_error(inter, e)

    # ────────────────────────────────────────────────────────────────────
    # limitbreak
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="limitbreak", description="Break through level limits!")
    @app_commands.describe(esprit_id="Esprit ID to limit break")
    async def limitbreak(self, inter: discord.Interaction, esprit_id: str):
        try:
            await inter.response.defer(ephemeral=True)

            async with get_session() as s:
            # Get user and esprit
                user = await s.get(User, str(inter.user.id))
                if not user:
                    return await inter.followup.send("❌ User not found!", ephemeral=True)

                stmt = (
                    select(UserEsprit)
                    .where(UserEsprit.id == esprit_id)
                    .options(selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner))
                )
                esprit = (await s.execute(stmt)).scalar_one_or_none()
            
                if not esprit or esprit.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Esprit not found or not yours!", ephemeral=True)

                # Check if can limit break
                can_break = esprit.can_limit_break()
                if not can_break["can_break"]:
                    if can_break["reason"] == "not_at_cap":
                        current_cap = esprit.get_current_level_cap()
                        return await inter.followup.send(
                            f"❌ {esprit.esprit_data.name} must be at level {current_cap} to limit break!\n"
                            f"Current level: {esprit.current_level}"
                        )
                    elif can_break["reason"] == "at_rarity_maximum":
                        return await inter.followup.send(
                            f"❌ {esprit.esprit_data.name} is already at maximum level for {esprit.esprit_data.rarity} rarity!"
                        )
                    elif can_break["reason"] == "insufficient_player_level":  # ADD THIS
                        return await inter.followup.send(
                            f"❌ Your player level is too low! Level up your player to unlock higher Esprit caps."
                        )

                # Get costs
                cost = esprit.get_limit_break_cost()
            
                # Check resources
                if user.essence < cost["essence"]:
                    return await inter.followup.send(
                        f"❌ Need {cost['essence']:,} Essence (you have {user.essence:,})"
                    )
                if user.moonglow < cost["moonglow"]:
                    return await inter.followup.send(
                        f"❌ Need {cost['moonglow']:,} Moonglow (you have {user.moonglow:,})"
                    )

                # Perform limit break
                old_power = esprit.calculate_power()
                old_cap = esprit.get_current_level_cap()
                old_multiplier = esprit.stat_boost_multiplier

                # Deduct costs
                user.essence -= cost["essence"]
                user.moonglow -= cost["moonglow"]

                # Apply limit break
                esprit.stat_boost_multiplier *= 1.1  # 10% boost
                esprit.limit_breaks_performed += 1
                esprit.current_hp = esprit.calculate_stat('hp')  # Heal to new max

                new_power = esprit.calculate_power()
                new_cap = esprit.get_current_level_cap()

                await s.commit()

                # Success embed
                embed = discord.Embed(
                    title="🔓 LIMIT BREAK SUCCESSFUL!",
                    description=f"**{esprit.esprit_data.name}** has transcended their limits!",
                    color=discord.Color.gold()
                )

                embed.add_field(
                    name="💪 Power Increase",
                    value=f"{old_power:,} → {new_power:,} Sigil\n(+{new_power - old_power:,})",
                    inline=True
                )

                embed.add_field(
                    name="📈 New Level Cap", 
                    value=f"Can now reach level **{new_cap}**",
                    inline=True
                )

                embed.add_field(
                    name="💰 Cost Paid",
                    value=f"{cost['essence']:,} Essence\n{cost['moonglow']:,} Moonglow",
                    inline=True
                )

                embed.add_field(
                    name="🔥 Total Limit Breaks",
                    value=f"**{esprit.limit_breaks_performed}** performed\nStat multiplier: **{esprit.stat_boost_multiplier:.2f}x**",
                    inline=True
                )

                await self._invalidate(str(inter.user.id))
                await inter.followup.send(embed=embed)

        except Exception as e:
            await self._handle_command_error(inter, e)

    # ────────────────────────────────────────────────────────────────────
    # upgrade (UPDATED for new system)
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="upgrade", description="Spend XP to level up Esprit.")
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
        try:
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
                    .options(selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner))
                    .with_for_update()
                )
                ue = (await s.execute(stmt)).scalar_one_or_none()
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("❌ Not found / not yours.", ephemeral=True)

                user = await s.get(User, str(inter.user.id), with_for_update=True)

                # CRITICAL: Get actual rarity-based level cap
                rarity_cap = RARITY_LEVEL_CAPS.get(ue.esprit_data.rarity, 100)
                
                # Calculate current level cap with limit breaks
                current_level_cap = ue.get_current_level_cap()                
                # ENFORCE LEVEL CAP - cannot exceed current cap
                if ue.current_level >= current_level_cap:
                    return await inter.followup.send(
                        f"❌ **{ue.esprit_data.name}** is at level cap ({current_level_cap}).\n"
                        f"**Rarity Cap:** {rarity_cap} | **Limit Breaks:** {ue.limit_breaks_performed}\n"
                        f"Use `/esprit limitbreak` to increase the cap!",
                        ephemeral=True
                    )

                # Calculate how many levels we can actually add
                max_possible_levels = current_level_cap - ue.current_level
                actual_levels_to_add = min(levels, max_possible_levels)
                
                if actual_levels_to_add <= 0:
                    return await inter.followup.send(
                        f"❌ Cannot level up. Already at cap ({current_level_cap}).", 
                        ephemeral=True
                    )

                target_level = ue.current_level + actual_levels_to_add

                # Calculate XP cost for levels
                total_xp_needed = 0
                for lvl in range(ue.current_level, target_level):
                    total_xp_needed += int(50 * ((lvl + 1) ** 1.3))

                if ue.current_xp < total_xp_needed:
                    return await inter.followup.send(
                        f"❌ Need {total_xp_needed:,} XP (you have {ue.current_xp:,})", 
                        ephemeral=True
                    )

                # Apply level up
                old_level = ue.current_level
                old_power = ue.calculate_power()
                
                ue.current_xp -= total_xp_needed
                ue.current_level = target_level
                ue.current_hp = ue.calculate_stat('hp')

                new_power = ue.calculate_power()

                s.add_all([user, ue])
                await s.commit()
                await self._invalidate(str(inter.user.id))

                # Show warning if user tried to add more levels than possible
                warning = ""
                if actual_levels_to_add < levels:
                    warning = f"\n⚠️ Could only add {actual_levels_to_add} levels due to level cap."

                await inter.followup.send(
                    embed=discord.Embed(
                        title="⭐ Upgrade Complete",
                        description=f"{ue.esprit_data.name} → Lvl {target_level}{warning}",
                        color=discord.Color.gold(),
                    )
                    .add_field(name="Levels Gained", value=f"{actual_levels_to_add}")
                    .add_field(name="XP Spent", value=f"{total_xp_needed:,}")
                    .add_field(name="New HP", value=f"{ue.current_hp:,}")
                    .add_field(name="Power Change", value=f"{old_power:,} → {new_power:,}")
                    .add_field(name="Level Cap", value=f"{target_level}/{current_level_cap}")
                )

        except Exception as e:
            await self._handle_command_error(inter, e)

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
        try:
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
                        getattr(user, 'active_esprit_id', None),
                        getattr(user, 'support1_esprit_id', None),
                        getattr(user, 'support2_esprit_id', None),
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
                    getattr(user, 'active_esprit_id', None),
                    getattr(user, 'support1_esprit_id', None),
                    getattr(user, 'support2_esprit_id', None),
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

        except Exception as e:
            await self._handle_command_error(inter, e)

    # ── internal helper for bulk dissolve ──────────────────────────────────
    async def _process_bulk_dissolve(self, inter: discord.Interaction, ids: Set[str]):
        try:
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
        except Exception as e:
            logger.error(f"Error in bulk dissolve: {e}")
            await inter.followup.send("❌ Error processing bulk dissolve.", ephemeral=True)

    # ── reward calculator ──────────────────────────────────────────────────
    def _calc_rewards(self, esprits: List[UserEsprit]) -> Dict[str, int]:
        # Use hardcoded values since we're moving away from complex config manager
        dissolve_rewards = {
            "Common": {"moonglow": 50, "essence": 5},
            "Uncommon": {"moonglow": 125, "essence": 12},
            "Rare": {"moonglow": 300, "essence": 30},
            "Epic": {"moonglow": 750, "essence": 75},
            "Celestial": {"moonglow": 2000, "essence": 200},
            "Supreme": {"moonglow": 5000, "essence": 500},
            "Deity": {"moonglow": 12500, "essence": 1250}
        }
        
        totals = {"moonglow": 0, "essence": 0}
        for e in esprits:
            r = dissolve_rewards.get(e.esprit_data.rarity, {"moonglow": 0, "essence": 0})
            totals["moonglow"] += r["moonglow"]
            totals["essence"] += r["essence"]
        return totals

    # ────────────────────────────────────────────────────────────────────
    # search
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="search", description="Find Esprits by name.")
    async def search(self, inter: discord.Interaction, query: str):
        try:
            await inter.response.defer(ephemeral=True)
            esprits = await self._get_collection(str(inter.user.id))
            hits = [
                e
                for e in esprits
                if query.lower() in e.esprit_data.name.lower()
            ][:25]

            if not hits:
                return await inter.followup.send("No matches.", ephemeral=True)

            lines = []
            for e in hits:
                try:
                    level_cap = e.get_current_level_cap() if hasattr(e, 'get_current_level_cap') else RARITY_LEVEL_CAPS.get(e.esprit_data.rarity, 100)
                    power = e.calculate_power() if hasattr(e, 'calculate_power') else 0
                    lines.append(
                        f"`{e.id}` • {e.esprit_data.name} • "
                        f"Lvl {e.current_level}/{level_cap} • Sigil {power:,}"
                    )
                except Exception as ex:
                    logger.error(f"Error formatting search result for {e.id}: {ex}")
                    lines.append(f"`{e.id}` • {e.esprit_data.name} • Error loading data")

            await inter.followup.send(
                embed=discord.Embed(
                    title=f"🔍 Search ({len(hits)})", description="\n".join(lines)
                ),
                ephemeral=True,
            )
        except Exception as e:
            await self._handle_command_error(inter, e)

    # ────────────────────────────────────────────────────────────────────
    # compare
    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="compare", description="Compare two Esprits' Sigil and stats."
    )
    async def compare(
        self, inter: discord.Interaction, esprit_a: str, esprit_b: str
    ):
        try:
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
                try:
                    ed = ue.esprit_data
                    lb_info = f" (🔓{ue.limit_breaks_performed})" if hasattr(ue, 'limit_breaks_performed') and ue.limit_breaks_performed > 0 else ""
                    level_cap = ue.get_current_level_cap() if hasattr(ue, 'get_current_level_cap') else RARITY_LEVEL_CAPS.get(ed.rarity, 100)
                    power = ue.calculate_power() if hasattr(ue, 'calculate_power') else 0
                    
                    embed.add_field(
                        name=f"{ed.name} • Sigil {power:,}",
                        value=(
                            f"Lvl {ue.current_level}/{level_cap} | "
                            f"{ed.rarity} {self._rarity_emoji(ed.rarity)}{lb_info}"
                        ),
                        inline=False,
                    )
                except Exception as ex:
                    logger.error(f"Error comparing esprit {ue.id}: {ex}")
                    embed.add_field(
                        name="Error",
                        value="Failed to load esprit data",
                        inline=False,
                    )
            await inter.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await self._handle_command_error(inter, e)

    # ────────────────────────────────────────────────────────────────────
    # team sub-commands
    # ────────────────────────────────────────────────────────────────────
    async def team_view(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)
            async with get_session() as s:
                user = await s.get(User, str(inter.user.id))
                ids = [
                    getattr(user, 'active_esprit_id', None),
                    getattr(user, 'support1_esprit_id', None),
                    getattr(user, 'support2_esprit_id', None),
                ]
                # Filter out None values
                valid_ids = [id for id in ids if id is not None]
                
                if valid_ids:
                    stmt = (
                        select(UserEsprit)
                        .where(UserEsprit.id.in_(valid_ids))
                        .options(selectinload(UserEsprit.esprit_data))
                    )
                    esprits = {e.id: e for e in (await s.execute(stmt)).scalars().all()}
                else:
                    esprits = {}

            labels = ["Leader", "Support-1", "Support-2"]
            lines = []
            for label, _id in zip(labels, ids):
                if not _id:
                    lines.append(f"**{label}:** —")
                elif _id in esprits:
                    e = esprits[_id]
                    try:
                        power = e.calculate_power() if hasattr(e, 'calculate_power') else 0
                        lines.append(
                            f"**{label}:** {e.esprit_data.name} (Lvl {e.current_level}, Sigil {power:,})"
                        )
                    except Exception as ex:
                        logger.error(f"Error displaying team esprit {_id}: {ex}")
                        lines.append(f"**{label}:** {e.esprit_data.name} (Error loading stats)")
                else:
                    lines.append(f"**{label}:** (missing)")
            await inter.followup.send(
                embed=discord.Embed(title="🛡️ Team", description="\n".join(lines)),
                ephemeral=True,
            )
        except Exception as e:
            await self._handle_command_error(inter, e)

    async def team_set(
        self,
        inter: discord.Interaction,
        slot: TeamSlot,
        esprit_id: str,
    ):
        try:
            if slot not in {TeamSlot.leader, TeamSlot.support1, TeamSlot.support2}:
                return await inter.response.send_message("Invalid slot.", ephemeral=True)
            await inter.response.defer(ephemeral=True)

            async with get_session() as s:
                ue = await s.get(UserEsprit, esprit_id)
                if not ue or ue.owner_id != str(inter.user.id):
                    return await inter.followup.send("Bad ID / not yours.", ephemeral=True)

                user = await s.get(User, str(inter.user.id))
                if slot == TeamSlot.leader:
                    user.active_esprit_id = esprit_id
                elif slot == TeamSlot.support1:
                    user.support1_esprit_id = esprit_id
                else:
                    user.support2_esprit_id = esprit_id

                await s.commit()

            await self._invalidate(str(inter.user.id))

            await inter.followup.send("✅ Team updated.", ephemeral=True)
        except Exception as e:
            await self._handle_command_error(inter, e)

    async def team_optimize(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)
            esprits = await self._get_collection(str(inter.user.id))
            
            # Sort by power safely
            def safe_power(e):
                try:
                    return e.calculate_power() if hasattr(e, 'calculate_power') else 0
                except Exception:
                    return 0
            
            best = sorted(esprits, key=safe_power, reverse=True)[:3]
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
        except Exception as e:
            await self._handle_command_error(inter, e)

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
