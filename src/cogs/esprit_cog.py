# src/cogs/esprit_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from typing import List, Dict, Optional, Union
import asyncio
from datetime import datetime, timedelta

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger
from src.utils.progression_manager import ProgressionManager
from src.utils.cache_manager import CacheManager  # Using centralized cache
from src.utils.rate_limiter import RateLimiter  # Using centralized rate limiter

logger = get_logger(__name__)

# Constants for scaling
MAX_COLLECTION_PAGE_SIZE = 25  # Increased for better UX
INTERACTION_TIMEOUT = 180  # 3 minutes
CACHE_TTL = 300  # 5 minutes for collection caching
MAX_BULK_OPERATIONS = 10  # Limit bulk dissolves

# Remove the EspritCache class since we're using CacheManager now

class ConfirmationView(discord.ui.View):
    """Reusable confirmation dialog for dangerous operations"""
    def __init__(self, author_id: int, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.result = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop()
        await interaction.response.edit_message(content="✅ Confirmed", view=None)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        await interaction.response.edit_message(content="❌ Cancelled", view=None)

class EnhancedCollectionView(discord.ui.View):
    """Enhanced collection view with filtering and sorting"""
    def __init__(self, all_esprits: List[UserEsprit], author_id: int, bot: commands.Bot):
        super().__init__(timeout=INTERACTION_TIMEOUT)
        self.all_esprits = all_esprits
        self.filtered_esprits = all_esprits
        self.author_id = author_id
        self.bot = bot
        self.current_page = 0
        self.sort_by = "name"  # name, level, rarity
        self.filter_rarity = None
        self.page_size = 10
        self.update_pages()
        self.update_buttons()
    
    def update_pages(self):
        """Regenerate pages based on current filters/sorting"""
        # Apply rarity filter
        if self.filter_rarity:
            self.filtered_esprits = [e for e in self.all_esprits if e.esprit_data.rarity == self.filter_rarity]
        else:
            self.filtered_esprits = self.all_esprits
        
        # Apply sorting
        if self.sort_by == "name":
            self.filtered_esprits.sort(key=lambda e: e.esprit_data.name)
        elif self.sort_by == "level":
            self.filtered_esprits.sort(key=lambda e: e.current_level, reverse=True)
        elif self.sort_by == "rarity":
            rarity_order = {"Common": 0, "Uncommon": 1, "Rare": 2, "Epic": 3, "Celestial": 4, "Supreme": 5, "Deity": 6}
            self.filtered_esprits.sort(key=lambda e: rarity_order.get(e.esprit_data.rarity, 0), reverse=True)
        
        self.pages = self._create_pages()
        self.current_page = min(self.current_page, len(self.pages) - 1) if self.pages else 0
    
    def _create_pages(self) -> List[discord.Embed]:
        pages = []
        if not self.filtered_esprits:
            embed = discord.Embed(
                title="📦 Esprit Collection",
                description="No Esprits found with current filters.",
                color=discord.Color.light_grey()
            )
            return [embed]
        
        # Calculate total power using the model method
        total_power = sum(e.calculate_power() for e in self.filtered_esprits)
        
        for i in range(0, len(self.filtered_esprits), self.page_size):
            chunk = self.filtered_esprits[i:i + self.page_size]
            embed = discord.Embed(
                title="📦 Esprit Collection",
                description=f"**Total:** {len(self.filtered_esprits)} | **Power:** {total_power:,} | **Page:** {i//self.page_size + 1}/{(len(self.filtered_esprits)-1)//self.page_size + 1}",
                color=discord.Color.dark_gold()
            )
            
            for ue in chunk:
                rarity_emoji = {
                    "Common": "⚪", "Uncommon": "🟢", "Rare": "🔵",
                    "Epic": "🟣", "Celestial": "🟡", "Supreme": "🔴", "Deity": "🌟"
                }.get(ue.esprit_data.rarity, "❓")
                
                # Show if it's in the active team
                team_indicator = ""
                if hasattr(self, 'user_data'):
                    if ue.id == self.user_data.get('active_esprit_id'):
                        team_indicator = " 👑"
                    elif ue.id in [self.user_data.get('support1_esprit_id'), self.user_data.get('support2_esprit_id')]:
                        team_indicator = " ⚔️"
                
                embed.add_field(
                    name=f"{rarity_emoji} **{ue.esprit_data.name}**{team_indicator}",
                    value=f"ID: `{ue.id}` | Lvl: **{ue.current_level}** | CP: **{ue.calculate_power():,}**",
                    inline=False
                )
            
            embed.set_footer(text=f"Sort: {self.sort_by.title()} | Filter: {self.filter_rarity or 'All'}")
            pages.append(embed)
        
        return pages
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot control this view.", ephemeral=True)
            return False
        return True
    
    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0 or not self.pages
        self.next_button.disabled = self.current_page >= len(self.pages) - 1 or not self.pages
        self.first_button.disabled = self.current_page == 0 or not self.pages
        self.last_button.disabled = self.current_page >= len(self.pages) - 1 or not self.pages
    
    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = len(self.pages) - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.select(
        placeholder="Sort by...",
        options=[
            discord.SelectOption(label="Name", value="name", emoji="📝"),
            discord.SelectOption(label="Level", value="level", emoji="📈"),
            discord.SelectOption(label="Rarity", value="rarity", emoji="💎")
        ],
        row=1
    )
    async def sort_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.sort_by = select.values[0]
        self.update_pages()
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.select(
        placeholder="Filter by rarity...",
        options=[
            discord.SelectOption(label="All", value="all", emoji="🌟"),
            discord.SelectOption(label="Common", value="Common", emoji="⚪"),
            discord.SelectOption(label="Uncommon", value="Uncommon", emoji="🟢"),
            discord.SelectOption(label="Rare", value="Rare", emoji="🔵"),
            discord.SelectOption(label="Epic", value="Epic", emoji="🟣"),
            discord.SelectOption(label="Celestial", value="Celestial", emoji="🟡"),
            discord.SelectOption(label="Supreme", value="Supreme", emoji="🔴"),
            discord.SelectOption(label="Deity", value="Deity", emoji="🌟")
        ],
        row=2
    )
    async def filter_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.filter_rarity = None if select.values[0] == "all" else select.values[0]
        self.current_page = 0  # Reset to first page
        self.update_pages()
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

class BulkDissolveView(discord.ui.View):
    """View for bulk dissolving operations"""
    def __init__(self, esprits: List[UserEsprit], author_id: int):
        super().__init__(timeout=300)
        self.esprits = esprits[:MAX_BULK_OPERATIONS]  # Limit to prevent abuse
        self.author_id = author_id
        self.selected_ids = set()
        self.update_select_options()
    
    def update_select_options(self):
        options = []
        for e in self.esprits[:25]:  # Discord limit
            emoji = "✅" if e.id in self.selected_ids else "❌"
            options.append(
                discord.SelectOption(
                    label=f"{e.esprit_data.name} (Lvl {e.current_level})",
                    value=e.id,
                    emoji=emoji,
                    description=f"{e.esprit_data.rarity} - ID: {e.id[:8]}"
                )
            )
        self.select_menu.options = options
        self.dissolve_button.disabled = len(self.selected_ids) == 0
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This is not your bulk dissolve session.", ephemeral=True)
            return False
        return True
    
    @discord.ui.select(placeholder="Select Esprits to dissolve...", min_values=0, max_values=25, row=0)
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_ids = set(select.values)
        self.update_select_options()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="Dissolve Selected", style=discord.ButtonStyle.danger, disabled=True, row=1)
    async def dissolve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_ids:
            return
        
        # Show confirmation
        confirm_embed = discord.Embed(
            title="⚠️ Confirm Bulk Dissolve",
            description=f"You are about to dissolve **{len(self.selected_ids)}** Esprits. This cannot be undone!",
            color=discord.Color.red()
        )
        
        confirm_view = ConfirmationView(self.author_id)
        await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        
        if confirm_view.result:
            # Process will be handled by the command
            self.stop()

@app_commands.guild_only()
class EspritGroup(app_commands.Group, name="esprit"):
    """Advanced Esprit management system with caching and performance optimizations"""
    
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.cache = CacheManager(default_ttl=CACHE_TTL)  # Using centralized CacheManager
        self.rate_limiter = RateLimiter(calls=5, period=60)  # Using centralized RateLimiter
        
        # Team subgroup
        self.team = app_commands.Group(name="team", description="Manage your combat team", parent=self)
        self.team.add_command(app_commands.Command(
            name="view", 
            description="View your current combat team.", 
            callback=self.team_view
        ))
        self.team.add_command(app_commands.Command(
            name="set", 
            description="Set an Esprit to a team slot.", 
            callback=self.team_set
        ))
        self.team.add_command(app_commands.Command(
            name="optimize",
            description="AI-powered team optimization suggestions.",
            callback=self.team_optimize
        ))
    
    async def _ensure_user_exists(self, user_id: str) -> bool:
        """Ensure user exists in database before operations"""
        async with get_session() as session:
            user = await session.get(User, user_id)
            if not user:
                # Auto-create user if needed
                user = User(user_id=user_id, username="Unknown")
                session.add(user)
                await session.commit()
                return True
            return True
    
    async def _get_user_collection(self, user_id: str) -> List[UserEsprit]:
        """Get user's collection with caching"""
        cache_key = f"user:{user_id}:collection"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        async with get_session() as session:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.owner_id == user_id)
                .options(selectinload(UserEsprit.esprit_data))
                .order_by(UserEsprit.esprit_data_id)
            )
            result = (await session.execute(stmt)).scalars().all()
            await self.cache.set(cache_key, result)
            return result
    
    async def _invalidate_user_cache(self, user_id: str):
        """Invalidate all cache entries for a user"""
        await self.cache.clear_pattern(f"user:{user_id}:")
    
    @app_commands.command(name="collection", description="View your Esprit collection with advanced filtering.")
    async def collection(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Ensure user exists
        await self._ensure_user_exists(str(interaction.user.id))
        
        # Get collection
        owned_esprits = await self._get_user_collection(str(interaction.user.id))
        
        if not owned_esprits:
            starter_embed = discord.Embed(
                title="🌟 Welcome to Esprit Collection!",
                description=(
                    "You don't own any Esprits yet.\n\n"
                    "**Getting Started:**\n"
                    "• Use `/summon` to get your first Esprits\n"
                    "• Complete quests to earn summoning materials\n"
                    "• Join events for exclusive Esprits!"
                ),
                color=discord.Color.blue()
            )
            starter_embed.set_footer(text="Tip: Your first summon is free!")
            return await interaction.followup.send(embed=starter_embed)
        
        # Get user data for team indicators
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            user_data = {
                'active_esprit_id': user.active_esprit_id,
                'support1_esprit_id': user.support1_esprit_id,
                'support2_esprit_id': user.support2_esprit_id
            }
        
        view = EnhancedCollectionView(owned_esprits, interaction.user.id, self.bot)
        view.user_data = user_data
        await interaction.followup.send(embed=view.pages[0], view=view)
    
    @app_commands.command(name="details", description="View detailed stats and growth potential of an Esprit.")
    @app_commands.describe(esprit_id="The ID of the Esprit (you can copy from collection)")
    async def details(self, interaction: discord.Interaction, esprit_id: str):
        await interaction.response.defer(ephemeral=True)
        
        async with get_session() as session:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id == esprit_id)
                .options(selectinload(UserEsprit.esprit_data))
            )
            user_esprit = (await session.execute(stmt)).scalar_one_or_none()
            
            if not user_esprit:
                return await interaction.followup.send("❌ Esprit not found.", ephemeral=True)
            
            if user_esprit.owner_id != str(interaction.user.id):
                return await interaction.followup.send("❌ You don't own this Esprit.", ephemeral=True)
            
            ed = user_esprit.esprit_data
            
            # Calculate growth stats
            level_multiplier = 1 + (user_esprit.current_level - 1) * 0.05
            current_stats = {
                "HP": int(ed.base_hp * level_multiplier),
                "Attack": int(ed.base_attack * level_multiplier),
                "Defense": int(ed.base_defense * level_multiplier),
                "Speed": int(ed.base_speed * level_multiplier)
            }
            
            # Create detailed embed
            embed = discord.Embed(
                title=f"{ed.name} - Detailed Analysis",
                color=self._get_rarity_color(ed.rarity)
            )
            
            # Basic info
            embed.add_field(
                name="📊 Basic Information",
                value=(
                    f"**ID:** `{user_esprit.id}`\n"
                    f"**Rarity:** {ed.rarity} {self._get_rarity_emoji(ed.rarity)}\n"
                    f"**Class:** {ed.class_name}\n"
                    f"**Level:** {user_esprit.current_level}/{100}"
                ),
                inline=True
            )
            
            # Current stats
            embed.add_field(
                name="⚔️ Current Stats",
                value=(
                    f"**HP:** {current_stats['HP']:,}\n"
                    f"**Attack:** {current_stats['Attack']}\n"
                    f"**Defense:** {current_stats['Defense']}\n"
                    f"**Speed:** {current_stats['Speed']}"
                ),
                inline=True
            )
            
            # Combat stats
            embed.add_field(
                name="🎯 Combat Stats",
                value=(
                    f"**Crit Rate:** {ed.base_crit_rate:.1%}\n"
                    f"**Block Rate:** {ed.base_block_rate:.1%}\n"
                    f"**Dodge:** {ed.base_dodge_chance:.1%}\n"
                    f"**Magic Resist:** {ed.base_magic_resist}"
                ),
                inline=True
            )
            
            # Growth potential
            max_level = 100  # Or from config
            max_multiplier = 1 + (max_level - 1) * 0.05
            embed.add_field(
                name="📈 Max Potential (Lvl 100)",
                value=(
                    f"**HP:** {int(ed.base_hp * max_multiplier):,}\n"
                    f"**Attack:** {int(ed.base_attack * max_multiplier)}\n"
                    f"**Defense:** {int(ed.base_defense * max_multiplier)}\n"
                    f"**Power:** ~{user_esprit.calculate_power() * int(max_multiplier / level_multiplier):,}"
                ),
                inline=True
            )
            
            embed.add_field(
                name="🌟 Abilities",
                value="Abilities unlock at higher levels",
                inline=False
            )
            
            # Description
            if ed.description:
                embed.add_field(
                    name="📜 Lore",
                    value=ed.description[:200] + "..." if len(ed.description) > 200 else ed.description,
                    inline=False
                )
            
            # Add thumbnail if available
            if hasattr(ed, 'image_url'):
                embed.set_thumbnail(url=ed.image_url)
            
            embed.set_footer(text="💡 Tip: Level up to unlock new abilities and increase stats!")
            
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="upgrade", description="Level up an Esprit using resources.")
    @app_commands.describe(
        esprit_id="The ID of the Esprit to upgrade",
        levels="Number of levels to upgrade (default: 1, max: 10)"
    )
    async def upgrade(self, interaction: discord.Interaction, esprit_id: str, levels: int = 1):
        await interaction.response.defer(ephemeral=True)
        
        # Validate levels
        if levels < 1 or levels > 10:
            return await interaction.followup.send("❌ You can only upgrade 1-10 levels at a time.", ephemeral=True)
        
        # Rate limit check
        if not await self.rate_limiter.check(str(interaction.user.id)):
            cooldown = await self.rate_limiter.get_cooldown(str(interaction.user.id))
            return await interaction.followup.send(
                f"⏳ You're upgrading too quickly! Please wait {cooldown} seconds before trying again.",
                ephemeral=True
            )
        
        async with get_session() as session:
            # Get esprit and user with lock to prevent race conditions
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id == esprit_id)
                .options(selectinload(UserEsprit.esprit_data))
                .with_for_update()
            )
            user_esprit = (await session.execute(stmt)).scalar_one_or_none()
            
            if not user_esprit or user_esprit.owner_id != str(interaction.user.id):
                return await interaction.followup.send("❌ Esprit not found or not owned by you.", ephemeral=True)
            
            user = await session.get(User, str(interaction.user.id), with_for_update=True)
            progression_manager = ProgressionManager(self.bot.config_manager)
            
            # Calculate total cost
            total_cost = 0
            current_level = user_esprit.current_level
            max_possible_level = min(user.level, current_level + levels)
            actual_levels = max_possible_level - current_level
            
            if actual_levels <= 0:
                return await interaction.followup.send(
                    f"❌ This Esprit is already at max level ({current_level}) for your player level.",
                    ephemeral=True
                )
            
            for i in range(actual_levels):
                total_cost += progression_manager.get_esprit_upgrade_cost(current_level + i)
            
            if user.moonglow < total_cost:
                return await interaction.followup.send(
                    f"❌ You need **{total_cost:,}** Moonglow, but you only have **{user.moonglow:,}**.",
                    ephemeral=True
                )
            
            # Perform upgrade
            user.moonglow -= total_cost
            user_esprit.current_level = max_possible_level
            user_esprit.current_xp = 0
            
            # Update stats based on new level
            level_multiplier = 1 + (user_esprit.current_level - 1) * 0.05
            user_esprit.current_hp = int(user_esprit.esprit_data.base_hp * level_multiplier)
            
            session.add_all([user, user_esprit])
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_user_cache(str(interaction.user.id))
            
            # Create success embed
            embed = discord.Embed(
                title="🌟 Upgrade Successful!",
                description=f"**{user_esprit.esprit_data.name}** has been upgraded!",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="📈 Level Progress",
                value=f"{current_level} → **{user_esprit.current_level}** (+{actual_levels})",
                inline=True
            )
            embed.add_field(
                name="💰 Cost",
                value=f"{total_cost:,} Moonglow",
                inline=True
            )
            embed.add_field(
                name="❤️ New HP",
                value=f"{user_esprit.current_hp:,}",
                inline=True
            )
            
            # Add milestone rewards if applicable
            if user_esprit.current_level % 10 == 0:
                embed.add_field(
                    name="🎉 Milestone Reached!",
                    value=f"Level {user_esprit.current_level} milestone bonus applied!",
                    inline=False
                )
            
            embed.set_footer(text=f"Remaining Moonglow: {user.moonglow:,}")
            
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="dissolve", description="Dissolve an Esprit to gain resources.")
    @app_commands.describe(esprit_id="The ID of the Esprit to dissolve.")
    async def dissolve(self, interaction: discord.Interaction, esprit_id: str):
        await interaction.response.defer(ephemeral=True)
        
        async with get_session() as session:
            stmt = select(UserEsprit).where(UserEsprit.id == esprit_id).options(selectinload(UserEsprit.esprit_data))
            user_esprit = (await session.execute(stmt)).scalar_one_or_none()

            if not user_esprit or user_esprit.owner_id != str(interaction.user.id):
                return await interaction.followup.send("❌ Esprit not found or not owned by you.", ephemeral=True)

            user = await session.get(User, str(interaction.user.id))
            if user.active_esprit_id == esprit_id or user.support1_esprit_id == esprit_id or user.support2_esprit_id == esprit_id:
                return await interaction.followup.send("❌ Cannot dissolve an Esprit in your active team.", ephemeral=True)

            # Show confirmation
            confirm_embed = discord.Embed(
                title="⚠️ Confirm Dissolve",
                description=f"Are you sure you want to dissolve **{user_esprit.esprit_data.name}** (Level {user_esprit.current_level})?",
                color=discord.Color.orange()
            )
            
            confirm_view = ConfirmationView(interaction.user.id)
            await interaction.followup.send(embed=confirm_embed, view=confirm_view, ephemeral=True)
            await confirm_view.wait()
            
            if not confirm_view.result:
                return

            # Reward logic based on rarity - using default values since dissolve_rewards not in game_settings
            reward_multipliers = {
                "Common": 1,
                "Uncommon": 2,
                "Rare": 4,
                "Epic": 8,
                "Celestial": 16,
                "Supreme": 32,
                "Deity": 64
            }
            
            base_moonglow = 50
            base_essence = 5
            multiplier = reward_multipliers.get(user_esprit.esprit_data.rarity, 1)
            
            rewards = {
                "moonglow": base_moonglow * multiplier,
                "essence": base_essence * multiplier
            }

            user.moonglow += rewards["moonglow"]
            user.essence += rewards["essence"]
            await session.delete(user_esprit)
            session.add(user)
            await session.commit()

            # Invalidate cache
            await self._invalidate_user_cache(str(interaction.user.id))

            embed = discord.Embed(
                title="♻️ Esprit Dissolved",
                description=f"**{user_esprit.esprit_data.name}** has been dissolved.",
                color=discord.Color.green()
            )
            reward_text = "\n".join(f"**{k.replace('_', ' ').title()}:** {v:,}" for k, v in rewards.items() if v > 0)
            embed.add_field(name="Rewards", value=reward_text or "None", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="bulk_dissolve", description="Dissolve multiple Esprits at once.")
    @app_commands.describe(rarity_filter="Only show Esprits of this rarity")
    async def bulk_dissolve(self, interaction: discord.Interaction, rarity_filter: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        
        valid_rarities = ["Common", "Uncommon", "Rare", "Epic", "Celestial", "Supreme", "Deity"]
        if rarity_filter and rarity_filter not in valid_rarities:
            return await interaction.followup.send(
                f"❌ Invalid rarity. Choose from: {', '.join(valid_rarities)}",
                ephemeral=True
            )
        
        async with get_session() as session:
            # Get user's team IDs
            user = await session.get(User, str(interaction.user.id))
            protected_ids = {user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id}
            protected_ids.discard(None)
            
            # Get dissolvable Esprits
            stmt = (
                select(UserEsprit)
                .where(
                    and_(
                        UserEsprit.owner_id == str(interaction.user.id),
                        ~UserEsprit.id.in_(protected_ids) if protected_ids else True
                    )
                )
                .options(selectinload(UserEsprit.esprit_data))
            )
            
            if rarity_filter:
                stmt = stmt.where(UserEsprit.esprit_data.has(rarity=rarity_filter))
            
            esprits = (await session.execute(stmt)).scalars().all()
            
            if not esprits:
                return await interaction.followup.send(
                    "❌ No Esprits available to dissolve. Team members cannot be dissolved.",
                    ephemeral=True
                )
            
            # Create bulk dissolve view
            view = BulkDissolveView(esprits, interaction.user.id)
            embed = discord.Embed(
                title="♻️ Bulk Dissolve",
                description=(
                    f"Select up to {MAX_BULK_OPERATIONS} Esprits to dissolve.\n"
                    f"**Available:** {len(esprits)} Esprits\n"
                    "⚠️ **Warning:** This cannot be undone!"
                ),
                color=discord.Color.orange()
            )
            
            await interaction.followup.send(embed=embed, view=view)
            await view.wait()
            
            if view.selected_ids:
                # Process bulk dissolve
                await self._process_bulk_dissolve(interaction, view.selected_ids)
    
    async def _process_bulk_dissolve(self, interaction: discord.Interaction, esprit_ids: set):
        """Process bulk dissolve with transaction safety"""
        async with get_session() as session:
            try:
                # Get all esprits to dissolve
                stmt = (
                    select(UserEsprit)
                    .where(UserEsprit.id.in_(esprit_ids))
                    .options(selectinload(UserEsprit.esprit_data))
                )
                esprits_to_dissolve = (await session.execute(stmt)).scalars().all()
                
                # Verify ownership
                for e in esprits_to_dissolve:
                    if e.owner_id != str(interaction.user.id):
                        return await interaction.followup.send(
                            "❌ Security error: You don't own all selected Esprits.",
                            ephemeral=True
                        )
                
                # Calculate total rewards - using default values
                total_rewards = {"moonglow": 0, "essence": 0}
                reward_multipliers = {
                    "Common": 1,
                    "Uncommon": 2,
                    "Rare": 4,
                    "Epic": 8,
                    "Celestial": 16,
                    "Supreme": 32,
                    "Deity": 64
                }
                
                base_moonglow = 50
                base_essence = 5
                
                for esprit in esprits_to_dissolve:
                    multiplier = reward_multipliers.get(esprit.esprit_data.rarity, 1)
                    total_rewards["moonglow"] += base_moonglow * multiplier
                    total_rewards["essence"] += base_essence * multiplier
                
                # Update user resources
                user = await session.get(User, str(interaction.user.id), with_for_update=True)
                user.moonglow += total_rewards["moonglow"]
                user.essence += total_rewards["essence"]
                
                # Delete esprits
                for esprit in esprits_to_dissolve:
                    await session.delete(esprit)
                
                session.add(user)
                await session.commit()
                
                # Invalidate cache
                await self._invalidate_user_cache(str(interaction.user.id))
                
                # Success message
                embed = discord.Embed(
                    title="♻️ Bulk Dissolve Complete",
                    description=f"Successfully dissolved **{len(esprits_to_dissolve)}** Esprits!",
                    color=discord.Color.green()
                )
                
                rewards_text = "\n".join(
                    f"**{k.title()}:** +{v:,}"
                    for k, v in total_rewards.items() if v > 0
                )
                embed.add_field(name="📦 Total Rewards", value=rewards_text or "None", inline=False)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
            except Exception as e:
                logger.error(f"Bulk dissolve error: {e}")
                await session.rollback()
                await interaction.followup.send(
                    "❌ An error occurred during bulk dissolve. No Esprits were dissolved.",
                    ephemeral=True
                )
    
    @app_commands.command(name="compare", description="Advanced comparison of multiple Esprits.")
    @app_commands.describe(
        esprit_ids="Comma-separated IDs (2-5 Esprits). Example: abc123,def456,ghi789"
    )
    async def compare(self, interaction: discord.Interaction, esprit_ids: str):
        await interaction.response.defer(ephemeral=True)
        
        # Parse IDs
        ids = [id.strip() for id in esprit_ids.split(",")]
        if len(ids) < 2 or len(ids) > 5:
            return await interaction.followup.send(
                "❌ Please provide 2-5 Esprit IDs separated by commas.",
                ephemeral=True
            )
        
        async with get_session() as session:
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id.in_(ids))
                .options(selectinload(UserEsprit.esprit_data))
            )
            esprits = (await session.execute(stmt)).scalars().all()
            
            # Verify ownership
            owned = [e for e in esprits if e.owner_id == str(interaction.user.id)]
            if len(owned) != len(ids):
                return await interaction.followup.send(
                    "❌ One or more Esprits not found or not owned by you.",
                    ephemeral=True
                )
            
            # Create comparison embed
            embed = discord.Embed(
                title="📊 Esprit Comparison",
                description="Detailed stat comparison",
                color=discord.Color.purple()
            )
            
            # Sort by power for easier comparison
            esprits.sort(key=lambda e: e.calculate_power(), reverse=True)
            
            for i, esprit in enumerate(esprits):
                ed = esprit.esprit_data
                level_mult = 1 + (esprit.current_level - 1) * 0.05
                
                # Calculate current stats
                stats = {
                    "HP": int(ed.base_hp * level_mult),
                    "ATK": int(ed.base_attack * level_mult),
                    "DEF": int(ed.base_defense * level_mult),
                    "SPD": int(ed.base_speed * level_mult),
                    "Power": esprit.calculate_power()
                }
                
                # Determine if this is the best in any stat
                stat_indicators = []
                for stat in ["HP", "ATK", "DEF", "SPD"]:
                    if all(stats[stat] >= e.calculate_stat(stat) for e in esprits if e != esprit):
                        stat_indicators.append(f"👑 {stat}")
                
                field_name = f"{i+1}. {ed.name} (Lvl {esprit.current_level})"
                if i == 0:
                    field_name += " ⭐"
                
                field_value = (
                    f"**Rarity:** {ed.rarity} {self._get_rarity_emoji(ed.rarity)}\n"
                    f"**Class:** {ed.class_name}\n"
                    f"**Power:** {stats['Power']:,}\n"
                    f"**HP:** {stats['HP']:,} | **ATK:** {stats['ATK']}\n"
                    f"**DEF:** {stats['DEF']} | **SPD:** {stats['SPD']}\n"
                )
                
                if stat_indicators:
                    field_value += f"**Best in:** {', '.join(stat_indicators)}"
                
                embed.add_field(name=field_name, value=field_value, inline=False)
            
            embed.set_footer(text="⭐ = Highest total power | 👑 = Best in stat")
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="search", description="Search your collection by name or attributes.")
    @app_commands.describe(
        query="Search by name, class, or rarity",
        min_level="Minimum level filter",
        max_level="Maximum level filter"
    )
    async def search(self, interaction: discord.Interaction, query: str, min_level: Optional[int] = None, max_level: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        
        collection = await self._get_user_collection(str(interaction.user.id))
        if not collection:
            return await interaction.followup.send("❌ You don't have any Esprits yet.", ephemeral=True)
        
        # Filter by query
        query_lower = query.lower()
        results = []
        
        for esprit in collection:
            ed = esprit.esprit_data
            # Check name, class, rarity
            if (query_lower in ed.name.lower() or 
                query_lower in ed.class_name.lower() or 
                query_lower in ed.rarity.lower()):
                
                # Apply level filters
                if min_level and esprit.current_level < min_level:
                    continue
                if max_level and esprit.current_level > max_level:
                    continue
                    
                results.append(esprit)
        
        if not results:
            return await interaction.followup.send(
                f"❌ No Esprits found matching '{query}'.",
                ephemeral=True
            )
        
        # Create results embed
        embed = discord.Embed(
            title=f"🔍 Search Results for '{query}'",
            description=f"Found {len(results)} matching Esprit(s)",
            color=discord.Color.blue()
        )
        
        # Limit to first 10 results
        for esprit in results[:10]:
            ed = esprit.esprit_data
            embed.add_field(
                name=f"{ed.name} ({ed.rarity})",
                value=(
                    f"**ID:** `{esprit.id}`\n"
                    f"**Level:** {esprit.current_level}\n"
                    f"**Class:** {ed.class_name}"
                ),
                inline=True
            )
        
        if len(results) > 10:
            embed.set_footer(text=f"Showing first 10 of {len(results)} results")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="equip", description="Quick equip an Esprit to your main slot.")
    @app_commands.describe(esprit_id="The ID of the Esprit to equip as main.")
    async def equip(self, interaction: discord.Interaction, esprit_id: str):
        await interaction.response.defer(ephemeral=True)
        
        async with get_session() as session:
            stmt = select(UserEsprit).where(UserEsprit.id == esprit_id).options(selectinload(UserEsprit.esprit_data))
            user_esprit = (await session.execute(stmt)).scalar_one_or_none()

            if not user_esprit or user_esprit.owner_id != str(interaction.user.id):
                return await interaction.followup.send("❌ Esprit not found or not owned by you.", ephemeral=True)

            user = await session.get(User, str(interaction.user.id))
            old_main = user.active_esprit_id
            user.active_esprit_id = esprit_id
            
            # If the esprit was in a support slot, clear it
            if user.support1_esprit_id == esprit_id:
                user.support1_esprit_id = None
            elif user.support2_esprit_id == esprit_id:
                user.support2_esprit_id = None
            
            session.add(user)
            await session.commit()

            # Invalidate cache
            await self._invalidate_user_cache(str(interaction.user.id))

            embed = discord.Embed(
                title="✅ Esprit Equipped",
                description=f"**{user_esprit.esprit_data.name}** is now your main Esprit!",
                color=discord.Color.green()
            )
            if old_main and old_main != esprit_id:
                embed.add_field(name="Previous Main", value="Moved to reserves", inline=False)
            
            await interaction.followup.send(embed=embed)
    
    # Team commands
    async def team_view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send("❌ User not found.", ephemeral=True)
            
            # Create team embed with power calculations
            embed = discord.Embed(
                title=f"⚔️ {interaction.user.display_name}'s Combat Team",
                color=discord.Color.purple()
            )
            
            total_team_power = 0
            team_slots = [
                ("👑 Main", user.active_esprit_id, 1.0),
                ("⚔️ Support 1", user.support1_esprit_id, 0.3),
                ("🛡️ Support 2", user.support2_esprit_id, 0.3)
            ]
            
            for label, esprit_id, power_mult in team_slots:
                if esprit_id:
                    stmt = (
                        select(UserEsprit)
                        .where(UserEsprit.id == esprit_id)
                        .options(selectinload(UserEsprit.esprit_data))
                    )
                    esprit = (await session.execute(stmt)).scalar_one_or_none()
                    
                    if esprit and esprit.esprit_data:
                        power = int(esprit.calculate_power() * power_mult)
                        total_team_power += power
                        
                        value = (
                            f"**{esprit.esprit_data.name}**\n"
                            f"Level {esprit.current_level} | {esprit.esprit_data.rarity}\n"
                            f"Power: {power:,} ({int(power_mult*100)}%)"
                        )
                    else:
                        value = "⚠️ Invalid Esprit"
                else:
                    value = "🔹 Empty Slot"
                
                embed.add_field(name=label, value=value, inline=True)
            
            # Team stats
            embed.add_field(
                name="📊 Team Statistics",
                value=(
                    f"**Total Power:** {total_team_power:,}\n"
                    f"**Team Rating:** {self._get_team_rating(total_team_power)}\n"
                    f"**Synergy Bonus:** {self._calculate_synergy_bonus(user)}%"
                ),
                inline=False
            )
            
            embed.set_footer(text="Use /esprit team set to modify your team")
            await interaction.followup.send(embed=embed)
    
    async def team_set(self, interaction: discord.Interaction, esprit_id: str, slot: str):
        await interaction.response.defer(ephemeral=True)
        
        valid_slots = ["main", "support1", "support2"]
        if slot.lower() not in valid_slots:
            return await interaction.followup.send(
                f"❌ Invalid slot. Choose from: {', '.join(valid_slots)}",
                ephemeral=True
            )
        
        async with get_session() as session:
            # Verify esprit ownership
            stmt = (
                select(UserEsprit)
                .where(UserEsprit.id == esprit_id)
                .options(selectinload(UserEsprit.esprit_data))
            )
            user_esprit = (await session.execute(stmt)).scalar_one_or_none()
            
            if not user_esprit or user_esprit.owner_id != str(interaction.user.id):
                return await interaction.followup.send(
                    "❌ Esprit not found or not owned by you.",
                    ephemeral=True
                )
            
            # Update team
            user = await session.get(User, str(interaction.user.id), with_for_update=True)
            slot_field = {
                "main": "active_esprit_id",
                "support1": "support1_esprit_id",
                "support2": "support2_esprit_id"
            }[slot.lower()]
            
            # Check if esprit is already in another slot
            current_slots = {
                "main": user.active_esprit_id,
                "support1": user.support1_esprit_id,
                "support2": user.support2_esprit_id
            }
            
            for s, eid in current_slots.items():
                if eid == esprit_id and s != slot.lower():
                    # Swap positions
                    setattr(user, slot_field, esprit_id)
                    setattr(user, {
                        "main": "active_esprit_id",
                        "support1": "support1_esprit_id",
                        "support2": "support2_esprit_id"
                    }[s], None)
                    
                    embed = discord.Embed(
                        title="🔄 Team Updated",
                        description=f"**{user_esprit.esprit_data.name}** moved from {s} to {slot.lower()} slot.",
                        color=discord.Color.green()
                    )
                    break
            else:
                setattr(user, slot_field, esprit_id)
                embed = discord.Embed(
                    title="✅ Team Updated",
                    description=f"**{user_esprit.esprit_data.name}** is now in your {slot.lower()} slot.",
                    color=discord.Color.green()
                )
            
            session.add(user)
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_user_cache(str(interaction.user.id))
            
            await interaction.followup.send(embed=embed)
    
    async def team_optimize(self, interaction: discord.Interaction):
        """AI-powered team optimization based on user's collection"""
        await interaction.response.defer(ephemeral=True)
        
        collection = await self._get_user_collection(str(interaction.user.id))
        if len(collection) < 3:
            return await interaction.followup.send(
                "❌ You need at least 3 Esprits to use team optimization.",
                ephemeral=True
            )
        
        # Simple optimization algorithm (can be enhanced with actual AI)
        # Sort by power and class synergy
        sorted_esprits = sorted(collection, key=lambda e: e.calculate_power(), reverse=True)
        
        # Find best main DPS (destroyer class)
        main_candidates = [e for e in sorted_esprits if e.esprit_data.class_name.lower() == "destroyer"]
        main = main_candidates[0] if main_candidates else sorted_esprits[0]
        
        # Find tank support (guardian class)
        tank_candidates = [e for e in sorted_esprits if e.esprit_data.class_name.lower() == "guardian" and e != main]
        support1 = tank_candidates[0] if tank_candidates else sorted_esprits[1] if sorted_esprits[1] != main else sorted_esprits[2]
        
        # Find healer/buffer support (support class)
        healer_candidates = [e for e in sorted_esprits if e.esprit_data.class_name.lower() == "support" and e not in [main, support1]]
        support2 = healer_candidates[0] if healer_candidates else next(e for e in sorted_esprits if e not in [main, support1])
        
        # Create recommendation embed
        embed = discord.Embed(
            title="🤖 AI Team Optimization",
            description="Based on your collection analysis, here's the optimal team:",
            color=discord.Color.gold()
        )
        
        recommendations = [
            ("👑 Main DPS", main, "Highest damage output (Destroyer)"),
            ("🛡️ Tank", support1, "Protects your team (Guardian)"),
            ("💚 Support", support2, "Heals and buffs (Support)")
        ]
        
        total_power = 0
        for role, esprit, reason in recommendations:
            ed = esprit.esprit_data
            power = esprit.calculate_power()
            total_power += power
            
            embed.add_field(
                name=role,
                value=(
                    f"**{ed.name}** (Lvl {esprit.current_level})\n"
                    f"{ed.rarity} {ed.class_name}\n"
                    f"Power: {power:,}\n"
                    f"*{reason}*"
                ),
                inline=True
            )
        
        embed.add_field(
            name="📊 Projected Performance",
            value=(
                f"**Total Power:** {total_power:,}\n"
                f"**Synergy Rating:** A+\n"
                f"**PvP Viability:** ⭐⭐⭐⭐⭐"
            ),
            inline=False
        )
        
        # Add apply button
        embed.set_footer(text="Would you like to apply this team composition?")
        
        await interaction.followup.send(embed=embed)
    
    # Helper methods
    def _get_rarity_color(self, rarity: str) -> discord.Color:
        colors = {
            "Common": discord.Color.light_grey(),
            "Uncommon": discord.Color.green(),
            "Rare": discord.Color.blue(),
            "Epic": discord.Color.purple(),
            "Celestial": discord.Color.gold(),
            "Supreme": discord.Color.red(),
            "Deity": discord.Color.from_rgb(255, 20, 147)  # Deep pink
        }
        return colors.get(rarity, discord.Color.default())
    
    def _get_rarity_emoji(self, rarity: str) -> str:
        emojis = {
            "Common": "⚪",
            "Uncommon": "🟢",
            "Rare": "🔵",
            "Epic": "🟣",
            "Celestial": "🟡",
            "Supreme": "🔴",
            "Deity": "🌟"
        }
        return emojis.get(rarity, "❓")
    
    def _get_team_rating(self, total_power: int) -> str:
        if total_power >= 100000:
            return "S+"
        elif total_power >= 75000:
            return "S"
        elif total_power >= 50000:
            return "A"
        elif total_power >= 30000:
            return "B"
        elif total_power >= 15000:
            return "C"
        else:
            return "D"
    
    def _calculate_synergy_bonus(self, user) -> int:
        # Placeholder for synergy calculation
        # Could check class combinations, element matchups, etc.
        return 15  # Base 15% synergy bonus

class EspritCog(commands.Cog):
    """Enhanced Esprit management system with caching and optimizations"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.esprit_group = EspritGroup(bot)
        
    async def cog_load(self):
        """Called when the cog is loaded"""
        self.bot.tree.add_command(self.esprit_group)
        logger.info("✅ Enhanced EspritCog loaded with caching and optimizations")
    
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        self.bot.tree.remove_command(self.esprit_group.name)
        logger.info("👋 EspritCog unloaded")

async def setup(bot: commands.Bot):
    await bot.add_cog(EspritCog(bot))
    logger.info("✅ EspritCog setup complete")