# src/cogs/admin_cog.py
import logging
from contextlib import asynccontextmanager
from typing import List, Tuple, Dict, Literal
import traceback

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func
from sqlmodel import delete, select, Session

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger

logger = get_logger(__name__)


# --- UI Component for Admin Help Dropdown ---
class AdminHelpSelect(discord.ui.Select):
    """The dropdown menu for selecting an admin command category."""
    def __init__(self, command_data: Dict):
        self.command_data = command_data
        options = [
            discord.SelectOption(
                label=data["name"],
                description=data["description"],
                emoji=data["emoji"],
                value=category
            ) for category, data in command_data.items()
        ]
        super().__init__(placeholder="Select a command category to view commands...", options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        data = self.command_data[category]

        embed = discord.Embed(
            title=f"{data['emoji']} {data['name']}",
            description=data["description"],
            color=discord.Color.orange()
        )

        for cmd in data["commands"]:
            embed.add_field(name=f"`{cmd['name']}`", value=f"**Usage**: `{cmd['usage']}`\n{cmd['desc']}", inline=False)
        
        embed.set_footer(text="All commands are owner-only.")
        await interaction.response.edit_message(embed=embed)


# --- UI View for Admin Help ---
class AdminHelpView(discord.ui.View):
    """The view that holds the admin help dropdown."""
    def __init__(self, author_id: int, command_data: Dict):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.add_item(AdminHelpSelect(command_data))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("This is not your help menu.", ephemeral=True)
            return False
        return True

class StatsView(discord.ui.View):
    """Interactive view for navigating different statistics pages."""
    def __init__(self, stats_data: dict, author_id: int):
        super().__init__(timeout=300)
        self.stats_data = stats_data
        self.author_id = author_id
        self.current_page = "overview"
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This is not your stats menu.", ephemeral=True)
            return False
        return True
    
    def get_embed(self) -> discord.Embed:
        """Get the embed for the current page."""
        if self.current_page == "overview":
            return self._create_overview_embed()
        elif self.current_page == "economy":
            return self._create_economy_embed()
        elif self.current_page == "esprits":
            return self._create_esprits_embed()
        elif self.current_page == "users":
            return self._create_users_embed()
    
    def _create_overview_embed(self) -> discord.Embed:
        """Create the overview statistics embed."""
        embed = discord.Embed(
            title="📊 Nyxa Global Statistics - Overview",
            description="Quick overview of key metrics",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        # Key Metrics
        embed.add_field(
            name="🔑 Key Metrics",
            value=f"**Total Users:** {self.stats_data['total_users']:,}\n"
                  f"**Active Today:** {self.stats_data['users_claimed_today']:,}\n"
                  f"**Total Esprits Owned:** {self.stats_data['total_esprits_owned']:,}\n"
                  f"**Total Nyxies:** {self.stats_data['total_nyxies']:,}",
            inline=True
        )
        
        # Bot Stats
        embed.add_field(
            name="🤖 Bot Status",
            value=f"**Guilds:** {self.stats_data['guild_count']:,}\n"
                  f"**Members:** {self.stats_data['member_count']:,}\n"
                  f"**Uptime:** {self.stats_data['uptime']}",
            inline=True
        )
        
        # Quick Stats
        embed.add_field(
            name="📈 Quick Stats",
            value=f"**Avg Level:** {self.stats_data['avg_level']:.1f}\n"
                  f"**Collection Rate:** {self.stats_data['collection_rate']:.1f}%\n"
                  f"**Active (7d):** {self.stats_data['active_users']:,}",
            inline=True
        )
        
        embed.set_footer(text="Click buttons below for detailed views")
        return embed
    
    def _create_economy_embed(self) -> discord.Embed:
        """Create the detailed economy statistics embed."""
        embed = discord.Embed(
            title="💰 Global Economy Statistics",
            description="Detailed breakdown of the in-game economy",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        
        # Total Currency
        embed.add_field(
            name="💎 Total Currency in Circulation",
            value=f"**Nyxies:** {self.stats_data['total_nyxies']:,}\n"
                  f"**Moonglow:** {self.stats_data['total_moonglow']:,}\n"
                  f"**Azurite Shards:** {self.stats_data['total_azurite']:,}\n"
                  f"**Essence:** {self.stats_data['total_essence']:,}\n"
                  f"**Loot Chests:** {self.stats_data['total_loot_chests']:,}",
            inline=True
        )
        
        # Per-User Averages
        if self.stats_data['total_users'] > 0:
            embed.add_field(
                name="📊 Per-User Averages",
                value=f"**Avg Nyxies:** {self.stats_data['total_nyxies']//self.stats_data['total_users']:,}\n"
                      f"**Avg Moonglow:** {self.stats_data['total_moonglow']//self.stats_data['total_users']:,}\n"
                      f"**Avg Azurite:** {self.stats_data['total_azurite']//self.stats_data['total_users']:,}\n"
                      f"**Avg Essence:** {self.stats_data['total_essence']//self.stats_data['total_users']:,}\n"
                      f"**Avg Loot Chests:** {self.stats_data['total_loot_chests']/self.stats_data['total_users']:.1f}",
                inline=True
            )
        
        # Wealth Distribution (if you want to add this)
        embed.add_field(
            name="💸 Economy Health",
            value=f"**Total Wealth:** {sum([self.stats_data['total_nyxies'], self.stats_data['total_moonglow'], self.stats_data['total_azurite'], self.stats_data['total_essence']]):,}\n"
                  f"**Items in Circulation:** {self.stats_data['total_loot_chests']:,}\n"
                  f"**Daily Claims Today:** {self.stats_data['users_claimed_today']:,}",
            inline=True
        )
        
        return embed
    
    def _create_esprits_embed(self) -> discord.Embed:
        """Create the detailed Esprit statistics embed."""
        embed = discord.Embed(
            title="🔮 Esprit Collection Statistics",
            description="Detailed breakdown of Esprit ownership and distribution",
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow()
        )
        
        # Overall Stats
        embed.add_field(
            name="📈 Collection Overview",
            value=f"**Total Owned:** {self.stats_data['total_esprits_owned']:,}\n"
                  f"**Unique Collected:** {self.stats_data['unique_esprits_owned']}/{self.stats_data['total_esprit_types']}\n"
                  f"**Collection Rate:** {self.stats_data['collection_rate']:.1f}%\n"
                  f"**Avg per User:** {self.stats_data['total_esprits_owned']/max(1, self.stats_data['total_users']):.1f}",
            inline=True
        )
        
        # Rarity Distribution
        if self.stats_data['rarity_distribution']:
            rarity_text = "\n".join([f"**{rarity}:** {count:,}" for rarity, count in sorted(self.stats_data['rarity_distribution'].items())])
            embed.add_field(
                name="🌟 Rarity Distribution",
                value=rarity_text or "No Esprits owned yet",
                inline=True
            )
        
        # Popular Esprit
        embed.add_field(
            name="🏆 Most Popular Esprit",
            value=self.stats_data['popular_esprit_name'],
            inline=True
        )
        
        return embed
    
    def _create_users_embed(self) -> discord.Embed:
        """Create the detailed user statistics embed."""
        embed = discord.Embed(
            title="👥 User Statistics",
            description="Detailed breakdown of user activity and progression",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # User Activity
        embed.add_field(
            name="📊 User Base",
            value=f"**Total Registered:** {self.stats_data['total_users']:,}\n"
                  f"**Active (7 days):** {self.stats_data['active_users']:,}\n"
                  f"**Active (today):** {self.stats_data['users_claimed_today']:,}\n"
                  f"**Activity Rate:** {(self.stats_data['active_users']/max(1, self.stats_data['total_users'])*100):.1f}%",
            inline=True
        )
        
        # Level Statistics
        embed.add_field(
            name="📈 Level Distribution",
            value=f"**Average Level:** {self.stats_data['avg_level']:.1f}\n"
                  f"**Highest Level:** {self.stats_data['max_level']}\n"
                  f"**Top Player:** {self.stats_data['top_player_mention']}",
            inline=True
        )
        
        # Engagement Metrics
        embed.add_field(
            name="🎮 Engagement",
            value=f"**Daily Claim Rate:** {(self.stats_data['users_claimed_today']/max(1, self.stats_data['total_users'])*100):.1f}%\n"
                  f"**Avg Esprits/User:** {self.stats_data['total_esprits_owned']/max(1, self.stats_data['total_users']):.1f}\n"
                  f"**Total XP Earned:** {self.stats_data.get('total_xp', 0):,}",
            inline=True
        )
        
        return embed
    
    @discord.ui.button(label="Overview", style=discord.ButtonStyle.primary, emoji="📊", row=0)
    async def overview_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "overview"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Economy", style=discord.ButtonStyle.success, emoji="💰", row=0)
    async def economy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "economy"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Esprits", style=discord.ButtonStyle.secondary, emoji="🔮", row=0)
    async def esprits_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "esprits"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Users", style=discord.ButtonStyle.secondary, emoji="👥", row=0)
    async def users_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "users"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # This would need to re-fetch the data - you'd need to pass a callback or reference to the command
        await interaction.response.send_message("♻️ Refreshing stats... Use `/admin stats` again for updated data.", ephemeral=True)

# --- Pagination View for Listing Esprits ---
class EspritPaginatorView(discord.ui.View):
    def __init__(self, author_id: int, user_display_name: str, all_esprits: List[Tuple[UserEsprit, EspritData]], per_page: int = 5):
        super().__init__(timeout=180)
        self.author_id, self.user_display_name, self.all_esprits, self.per_page = author_id, user_display_name, all_esprits, per_page
        self.current_page, self.total_pages = 0, (len(all_esprits) - 1) // per_page
        self.update_buttons()
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This is not your menu.", ephemeral=True)
            return False
        return True
        
    def get_page_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🔮 {self.user_display_name}'s Esprit Collection", color=discord.Color.purple())
        start, end = self.current_page * self.per_page, (self.current_page * self.per_page) + self.per_page
        description = "".join([f"**{ed.name}** (ID: `{ue.id}`)\n└ Lvl **{ue.current_level}** | Rarity: **{ed.rarity}**\n" for ue, ed in self.all_esprits[start:end]])
        embed.description = description
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages + 1} | Total Esprits: {len(self.all_esprits)}")
        return embed
        
    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= self.total_pages
        
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
        
    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)


# --- Main Admin Cog ---
@app_commands.guild_only()
class AdminCog(commands.Cog):
    """Owner-only administrative slash commands for bot management."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # --- Data for the /admin help command ---
        self.admin_commands_data = {
            "give": {
                "name": "🎁 Give Commands", 
                "emoji": "🎁", 
                "description": "Commands for adding currency or items to a user.",
                "commands": [
                    {"name": "/give nyxies", "usage": "<user> <amount>", "desc": "Adds nyxies to a user's balance."},
                    {"name": "/give moonglow", "usage": "<user> <amount>", "desc": "Adds moonglow to a user's balance."},
                    {"name": "/give azurite_shards", "usage": "<user> <amount>", "desc": "Adds azurite shards to a user's balance."},
                    {"name": "/give essence", "usage": "<user> <amount>", "desc": "Adds essence to a user's balance."},
                    {"name": "/give xp", "usage": "<user> <amount>", "desc": "Adds experience points to a user."},
                    {"name": "/give loot_chests", "usage": "<user> <amount>", "desc": "Adds loot chests to a user."},
                    {"name": "/give esprit", "usage": "<user> <esprit_name>", "desc": "Creates a new instance of an Esprit for a user."},
                ]
            },
            "remove": {
                "name": "➖ Remove Commands", 
                "emoji": "➖", 
                "description": "Commands for subtracting currency or items.",
                "commands": [
                    {"name": "/remove nyxies", "usage": "<user> <amount>", "desc": "Removes nyxies from a user, down to a minimum of 0."},
                    {"name": "/remove moonglow", "usage": "<user> <amount>", "desc": "Removes moonglow from a user, down to a minimum of 0."},
                    {"name": "/remove azurite_shards", "usage": "<user> <amount>", "desc": "Removes azurite shards from a user, down to a minimum of 0."},
                    {"name": "/remove essence", "usage": "<user> <amount>", "desc": "Removes essence from a user, down to a minimum of 0."},
                    {"name": "/remove xp", "usage": "<user> <amount>", "desc": "Removes XP from a user, down to a minimum of 0."},
                    {"name": "/remove loot_chests", "usage": "<user> <amount>", "desc": "Removes loot chests from a user, down to a minimum of 0."},
                    {"name": "/remove esprit", "usage": "<user> <esprit_id>", "desc": "Deletes a specific Esprit instance by its unique ID."},
                ]
            },
            "set": {
                "name": "⚙️ Set Commands", 
                "emoji": "⚙️", 
                "description": "Commands for setting an exact value.",
                "commands": [
                    {"name": "/set nyxies", "usage": "<user> <amount>", "desc": "Sets a user's nyxies to an exact amount."},
                    {"name": "/set moonglow", "usage": "<user> <amount>", "desc": "Sets a user's moonglow to an exact amount."},
                    {"name": "/set azurite_shards", "usage": "<user> <amount>", "desc": "Sets a user's azurite shards to an exact amount."},
                    {"name": "/set essence", "usage": "<user> <amount>", "desc": "Sets a user's essence to an exact amount."},
                    {"name": "/set loot_chests", "usage": "<user> <amount>", "desc": "Sets a user's loot chests to an exact amount."},
                    {"name": "/set level", "usage": "<user> <level>", "desc": "Sets a user's level and resets their XP to 0."},
                    {"name": "/set esprit_level", "usage": "<esprit_id> <level>", "desc": "Sets a specific Esprit's level and resets its XP to 0."},
                ]
            },
            "reset": {
                "name": "♻️ Reset Commands", 
                "emoji": "♻️", 
                "description": "Commands for resetting data or cooldowns.",
                "commands": [
                    {"name": "/reset daily", "usage": "<user>", "desc": "Resets a user's `/daily` command cooldown."},
                    {"name": "/reset user_data", "usage": "<user> <confirmation>", "desc": "DANGEROUS: Wipes all data for a specific user."},
                ]
            },
            "utility": {
                "name": "🛠️ Utility Commands", 
                "emoji": "🛠️", 
                "description": "General-purpose administrative commands.",
                "commands": [
                    {"name": "/admin stats", "usage": "", "desc": "Shows comprehensive global bot statistics including users, economy, and Esprits."},
                    {"name": "/inspect", "usage": "<user>", "desc": "Shows a detailed embed of a user's database record."},
                    {"name": "/list users", "usage": "", "desc": "Lists the top 25 users by level."},
                    {"name": "/list esprits", "usage": "<user>", "desc": "Shows a paginated list of a user's Esprit collection."},
                    {"name": "/reload config", "usage": "", "desc": "Reloads the bot's configuration files from disk."},
                    {"name": "/reload esprits", "usage": "[force]", "desc": "Reloads Esprit data from JSON. Use force=True to update existing."},
                    {"name": "/reload cog", "usage": "<cog_name>", "desc": "Reloads a specific bot cog."},
                ]
            }
        }

    # --- Helper Context Manager ---
    @asynccontextmanager
    async def _get_user_context(self, interaction: discord.Interaction, user: discord.User):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ You are not the bot owner.", ephemeral=True)
            yield None, None
            return
        await interaction.response.defer(ephemeral=True)
        try:
            async with get_session() as session:
                user_obj = await session.get(User, str(user.id))
                if not user_obj:
                    await interaction.followup.send(f"❌ User {user.mention} has not registered.")
                    yield None, None
                else:
                    yield session, user_obj
                    await session.commit()
        except Exception as e:
            logger.error(f"Error in user command context for '{interaction.command.name}':", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ An unexpected error occurred: {e}")
            yield None, None

    # --- Helper for currency commands ---
    async def _give_currency(self, interaction: discord.Interaction, user: discord.User, amount: int, 
                           currency_type: Literal['nyxies', 'moonglow', 'azurite_shards', 'essence', 'xp']):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive.")
                return
            current_value = getattr(user_obj, currency_type)
            setattr(user_obj, currency_type, current_value + amount)
            session.add(user_obj)
            display_name = currency_type.replace('_', ' ').title()
            new_value = getattr(user_obj, currency_type)
            await interaction.followup.send(f"✅ Gave **{amount:,}** {display_name}. New balance: **{new_value:,}**.")
            logger.info(f"Gave {amount} {display_name} to {user} ({user.id}).")

    # --- Command Groups ---
    admin_group = app_commands.Group(name="admin", description="Core admin and bot management commands.")
    give_group = app_commands.Group(name="give", description="Give items or currency to a user")
    remove_group = app_commands.Group(name="remove", description="Remove items or currency from a user")
    set_group = app_commands.Group(name="set", description="Set a specific value for a user or esprit")
    reset_group = app_commands.Group(name="reset", description="Reset various data")
    list_group = app_commands.Group(name="list", description="List data from the database")
    reload_group = app_commands.Group(name="reload", description="Reload bot components")

    # --- Admin Help Command ---
    @admin_group.command(name="help", description="Interactive manual for all admin commands.")
    async def help(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ You are not the bot owner.", ephemeral=True)
        embed = discord.Embed(
            title="🛠️ Nyxa Admin Command Center",
            description="Select a category from the dropdown menu below to view its available commands and usage.",
            color=discord.Color.orange()
        )
        view = AdminHelpView(interaction.user.id, self.admin_commands_data)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @admin_group.command(name="stats", description="Display comprehensive global bot statistics")
    async def global_stats(self, interaction: discord.Interaction):
        """Show detailed global statistics about the bot's usage and economy."""
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            stats_data = {}
            
            async with get_session() as session:
                # User Statistics
                stats_data['total_users'] = (await session.execute(
                    select(func.count(User.user_id))
                )).scalar_one()
                
                # Level Statistics
                stats_data['avg_level'] = (await session.execute(
                    select(func.avg(User.level))
                )).scalar_one() or 0
                
                max_level_user = (await session.execute(
                    select(User).order_by(User.level.desc()).limit(1)
                )).scalar_one_or_none()
                
                if max_level_user:
                    stats_data['max_level'] = max_level_user.level
                    top_user = self.bot.get_user(int(max_level_user.user_id))
                    stats_data['top_player_mention'] = top_user.mention if top_user else f"ID: {max_level_user.user_id}"
                else:
                    stats_data['max_level'] = 0
                    stats_data['top_player_mention'] = "None"
                
                # Total XP
                stats_data['total_xp'] = (await session.execute(
                    select(func.sum(User.xp))
                )).scalar_one() or 0
                
                # Currency Statistics
                stats_data['total_nyxies'] = (await session.execute(
                    select(func.sum(User.nyxies))
                )).scalar_one() or 0
                
                stats_data['total_moonglow'] = (await session.execute(
                    select(func.sum(User.moonglow))
                )).scalar_one() or 0
                
                stats_data['total_azurite'] = (await session.execute(
                    select(func.sum(User.azurite_shards))
                )).scalar_one() or 0
                
                stats_data['total_essence'] = (await session.execute(
                    select(func.sum(User.essence))
                )).scalar_one() or 0
                
                stats_data['total_loot_chests'] = (await session.execute(
                    select(func.sum(User.loot_chests))
                )).scalar_one() or 0
                
                # Esprit Statistics
                stats_data['total_esprits_owned'] = (await session.execute(
                    select(func.count(UserEsprit.id))
                )).scalar_one()
                
                stats_data['unique_esprits_owned'] = (await session.execute(
                    select(func.count(func.distinct(UserEsprit.esprit_data_id)))
                )).scalar_one()
                
                stats_data['total_esprit_types'] = (await session.execute(
                    select(func.count(EspritData.esprit_id))
                )).scalar_one()
                
                stats_data['collection_rate'] = (stats_data['unique_esprits_owned'] / max(1, stats_data['total_esprit_types']) * 100)
                
                # Most popular Esprit
                popular_esprit_result = (await session.execute(
                    select(UserEsprit.esprit_data_id, func.count(UserEsprit.id).label('count'))
                    .group_by(UserEsprit.esprit_data_id)
                    .order_by(func.count(UserEsprit.id).desc())
                    .limit(1)
                )).first()
                
                if popular_esprit_result:
                    esprit_data = await session.get(EspritData, popular_esprit_result[0])
                    if esprit_data:
                        stats_data['popular_esprit_name'] = f"{esprit_data.name} ({popular_esprit_result[1]} owned)"
                else:
                    stats_data['popular_esprit_name'] = "None yet"
                
                # Rarity distribution
                stats_data['rarity_distribution'] = dict((await session.execute(
                    select(EspritData.rarity, func.count(UserEsprit.id))
                    .join(UserEsprit, UserEsprit.esprit_data_id == EspritData.esprit_id)
                    .group_by(EspritData.rarity)
                )).all())
                
                # Daily claim statistics
                stats_data['users_claimed_today'] = (await session.execute(
                    select(func.count(User.user_id))
                    .where(User.last_daily_claim != None)
                    .where(func.date(User.last_daily_claim) == func.date(func.current_timestamp()))
                )).scalar_one()
                
                # Active users (last 7 days)
                from datetime import datetime, timedelta
                seven_days_ago = datetime.utcnow() - timedelta(days=7)
                stats_data['active_users'] = (await session.execute(
                    select(func.count(User.user_id))
                    .where(User.last_daily_claim >= seven_days_ago)
                )).scalar_one()
            
            # Bot Information
            stats_data['guild_count'] = len(self.bot.guilds)
            stats_data['member_count'] = sum(g.member_count for g in self.bot.guilds)
            
            if hasattr(self.bot, 'start_time'):
                stats_data['uptime'] = discord.utils.format_dt(self.bot.start_time, 'R')
            else:
                stats_data['uptime'] = "Not tracked"
            
            # Create the view and send the initial embed
            view = StatsView(stats_data, interaction.user.id)
            embed = view.get_embed()
            
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error generating global stats:", exc_info=True)
            await interaction.followup.send(f"❌ Error generating statistics: {str(e)}", ephemeral=True)

    # --- System Commands ---
    @app_commands.command(name="inspect", description="Inspect a user's complete database record")
    async def inspect(self, interaction: discord.Interaction, user: discord.User):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                return await interaction.followup.send(f"❌ {user.mention} has no data.")
            esprit_count = (await session.execute(
                select(func.count(UserEsprit.id)).where(UserEsprit.owner_id == str(user.id))
            )).scalar_one()
        
        embed = discord.Embed(title=f"🔍 Inspect: {user.display_name}", color=discord.Color.gold())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User ID", value=f"`{user_obj.user_id}`", inline=False)
        embed.add_field(name="Level | XP", value=f"{user_obj.level} | {user_obj.xp:,}", inline=True)
        embed.add_field(name="Esprits", value=f"{esprit_count:,}", inline=True)
        embed.add_field(name="Nyxies | Moonglow", value=f"{user_obj.nyxies:,} | {user_obj.moonglow:,}", inline=True)
        embed.add_field(name="Azurite Shards", value=f"{user_obj.azurite_shards:,}", inline=True)
        embed.add_field(name="Essence", value=f"{user_obj.essence:,}", inline=True)
        embed.add_field(name="Loot Chests", value=f"{user_obj.loot_chests:,}", inline=True)
        embed.add_field(name="Last Daily", value=f"{discord.utils.format_dt(user_obj.last_daily_claim, 'R') if user_obj.last_daily_claim else 'Never'}", inline=False)
        embed.add_field(name="Created At", value=f"{discord.utils.format_dt(user_obj.created_at, 'F')}", inline=False)
        await interaction.followup.send(embed=embed)

    # --- Reload Commands ---
    @reload_group.command(name="config", description="Reload all configuration files")
    async def reload_config(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        try:
            self.bot.config_manager.reload()
            logger.info(f"CONFIG reloaded by owner {interaction.user}.")
            await interaction.response.send_message("✅ Configuration files reloaded.", ephemeral=True)
        except Exception as e:
            logger.error("Error reloading configs", exc_info=True)
            await interaction.response.send_message(f"❌ Could not reload configs: {e}", ephemeral=True)

    @reload_group.command(name="cog", description="Reload a specific cog")
    @app_commands.describe(cog_name="The name of the cog to reload (e.g., src.cogs.economy_cog)")
    async def reload_cog(self, interaction: discord.Interaction, cog_name: str):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(cog_name)
            logger.info(f"Cog '{cog_name}' reloaded successfully by {interaction.user}.")
            await interaction.followup.send(f"✅ Successfully reloaded `{cog_name}`.")
        except Exception as e:
            logger.error(f"Failed to reload cog '{cog_name}': {e}", exc_info=True)
            await interaction.followup.send(f"**Error reloading `{cog_name}`:**\n```py\n{traceback.format_exc()[:1900]}\n```")

    @reload_group.command(name="esprits", description="Reload Esprit data from JSON file")
    async def reload_esprits(self, interaction: discord.Interaction, force: bool = False):
        """Reload Esprit data from the JSON file into the database."""
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            from src.database.data_loader import EspritDataLoader
            loader = EspritDataLoader()
            count = await loader.load_esprits(force_reload=force)
            
            embed = discord.Embed(
                title="✅ Esprit Data Reloaded",
                description=f"Successfully loaded **{count:,}** Esprits from JSON.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Mode", 
                value="Force reload (updated existing)" if force else "Normal (new entries only)",
                inline=False
            )
            
            # Verify data integrity
            missing = await loader.verify_data_integrity()
            if missing:
                embed.add_field(
                    name="⚠️ Warning",
                    value=f"Found {len(missing)} Esprits in JSON but not in database",
                    inline=False
                )
            
            logger.info(f"ESPRITS reloaded by owner {interaction.user}. Count: {count}, Force: {force}")
            await interaction.followup.send(embed=embed)
            
        except FileNotFoundError:
            logger.error("Esprits JSON file not found")
            await interaction.followup.send("❌ Could not find `data/config/esprits.json` file!", ephemeral=True)
        except Exception as e:
            logger.error("Error reloading Esprits", exc_info=True)
            await interaction.followup.send(f"❌ Could not reload Esprits: {str(e)}", ephemeral=True)

    # --- Give Commands ---
    @give_group.command(name="nyxies", description="Give nyxies to a user")
    async def give_nyxies(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await self._give_currency(interaction, user, amount, 'nyxies')

    @give_group.command(name="moonglow", description="Give moonglow to a user")
    async def give_moonglow(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await self._give_currency(interaction, user, amount, 'moonglow')

    @give_group.command(name="azurite_shards", description="Give azurite shards to a user")
    async def give_azurite_shards(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await self._give_currency(interaction, user, amount, 'azurite_shards')

    @give_group.command(name="essence", description="Give essence to a user")
    async def give_essence(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await self._give_currency(interaction, user, amount, 'essence')

    @give_group.command(name="xp", description="Give XP to a user")
    async def give_xp(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await self._give_currency(interaction, user, amount, 'xp')

    @give_group.command(name="loot_chests", description="Give loot chests to a user")
    async def give_loot_chests(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive.")
                return
            user_obj.loot_chests += amount
            session.add(user_obj)
            await interaction.followup.send(f"✅ Gave **{amount:,}** loot chests. New balance: **{user_obj.loot_chests:,}**.")

    @give_group.command(name="esprit", description="Give a specific Esprit to a user by name")
    async def give_esprit(self, interaction: discord.Interaction, user: discord.User, esprit_name: str):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            if not await session.get(User, str(user.id)):
                return await interaction.followup.send(f"❌ {user.mention} must use /start first.")
            stmt = select(EspritData).where(func.lower(EspritData.name) == esprit_name.lower())
            esprit_data = (await session.execute(stmt)).scalars().first()
            if not esprit_data:
                return await interaction.followup.send(f"❌ No Esprit definition found for `{esprit_name}`.")
            new_esprit = UserEsprit(
                owner_id=str(user.id),
                esprit_data_id=esprit_data.esprit_id,
                current_level=1,
                current_xp=0,
                current_hp=esprit_data.base_hp
            )
            session.add(new_esprit)
            await session.commit()
            await session.refresh(new_esprit)
            await interaction.followup.send(f"✅ Gave **{esprit_data.name}** (ID: `{new_esprit.id}`) to {user.mention}.")

    # --- Remove Commands ---
    @remove_group.command(name="nyxies", description="Remove nyxies from a user")
    async def remove_nyxies(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive.")
                return
            user_obj.nyxies = max(0, user_obj.nyxies - amount)
            session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** nyxies. New balance: **{user_obj.nyxies:,}**.")

    @remove_group.command(name="moonglow", description="Remove moonglow from a user")
    async def remove_moonglow(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive.")
                return
            user_obj.moonglow = max(0, user_obj.moonglow - amount)
            session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** moonglow. New balance: **{user_obj.moonglow:,}**.")

    @remove_group.command(name="xp", description="Remove XP from a user")
    async def remove_xp(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive.")
                return
            user_obj.xp = max(0, user_obj.xp - amount)
            session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** XP. New balance: **{user_obj.xp:,}**.")

    @remove_group.command(name="azurite_shards", description="Remove azurite shards from a user")
    async def remove_azurite_shards(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive.")
                return
            user_obj.azurite_shards = max(0, user_obj.azurite_shards - amount)
            session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** azurite shards. New balance: **{user_obj.azurite_shards:,}**.")

    @remove_group.command(name="essence", description="Remove essence from a user")
    async def remove_essence(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive.")
                return
            user_obj.essence = max(0, user_obj.essence - amount)
            session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** essence. New balance: **{user_obj.essence:,}**.")

    @remove_group.command(name="loot_chests", description="Remove loot chests from a user")
    async def remove_loot_chests(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive.")
                return
            user_obj.loot_chests = max(0, user_obj.loot_chests - amount)
            session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** loot chests. New balance: **{user_obj.loot_chests:,}**.")

    @remove_group.command(name="esprit", description="Remove a specific Esprit from a user by its unique ID")
    async def remove_esprit(self, interaction: discord.Interaction, user: discord.User, esprit_id: str):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            stmt = select(UserEsprit).where(UserEsprit.id == esprit_id)
            esprit_to_remove = (await session.execute(stmt)).scalar_one_or_none()
            
            if not esprit_to_remove:
                return await interaction.followup.send(f"❌ No Esprit found with ID `{esprit_id}`.")
            if esprit_to_remove.owner_id != str(user.id):
                return await interaction.followup.send(f"❌ That Esprit does not belong to {user.mention}.")
            
            await session.delete(esprit_to_remove)
            await session.commit()
            await interaction.followup.send(f"✅ Removed Esprit ID `{esprit_id}` from {user.mention}.")

    # --- Set Commands ---
    @set_group.command(name="nyxies", description="Set a user's exact nyxies amount")
    async def set_nyxies(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount < 0:
                await interaction.followup.send("❌ Amount cannot be negative.")
                return
            user_obj.nyxies = amount
            session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s nyxies to **{amount:,}**.")

    @set_group.command(name="moonglow", description="Set a user's exact moonglow amount")
    async def set_moonglow(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount < 0:
                await interaction.followup.send("❌ Amount cannot be negative.")
                return
            user_obj.moonglow = amount
            session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s moonglow to **{amount:,}**.")

    @set_group.command(name="azurite_shards", description="Set a user's exact azurite shards amount")
    async def set_azurite_shards(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount < 0:
                await interaction.followup.send("❌ Amount cannot be negative.")
                return
            user_obj.azurite_shards = amount
            session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s azurite shards to **{amount:,}**.")

    @set_group.command(name="essence", description="Set a user's exact essence amount")
    async def set_essence(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount < 0:
                await interaction.followup.send("❌ Amount cannot be negative.")
                return
            user_obj.essence = amount
            session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s essence to **{amount:,}**.")

    @set_group.command(name="loot_chests", description="Set a user's exact loot chests amount")
    async def set_loot_chests(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if amount < 0:
                await interaction.followup.send("❌ Amount cannot be negative.")
                return
            user_obj.loot_chests = amount
            session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s loot chests to **{amount:,}**.")

    @set_group.command(name="level", description="Set a user's level and reset their XP")
    async def set_level(self, interaction: discord.Interaction, user: discord.User, level: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session:
                return
            if level <= 0:
                await interaction.followup.send("❌ Level must be positive.")
                return
            user_obj.level = level
            user_obj.xp = 0
            session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s level to **{level}** and reset XP to 0.")

    @set_group.command(name="esprit_level", description="Set the level for a specific Esprit instance")
    async def set_esprit_level(self, interaction: discord.Interaction, esprit_id: str, level: int):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        if level <= 0:
            return await interaction.response.send_message("❌ Level must be positive.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            stmt = select(UserEsprit).where(UserEsprit.id == esprit_id)
            user_esprit = (await session.execute(stmt)).scalar_one_or_none()

            if not user_esprit:
                return await interaction.followup.send(f"❌ No Esprit found with ID `{esprit_id}`.")
            
            user_esprit.current_level = level
            user_esprit.current_xp = 0
            session.add(user_esprit)
            await session.commit()
            await interaction.followup.send(f"✅ Set Esprit ID `{esprit_id}` to **Level {level}**.")
    
    # --- Reset Commands ---
    @reset_group.command(name="user_data")
    async def reset_user_data(self, interaction: discord.Interaction, user: discord.User, confirmation: str):
        # FIX: Correctly access the nested test_user_ids list
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        developer_settings = game_settings.get("developer", {})
        allowed_test_ids = [str(uid) for uid in developer_settings.get("test_user_ids", [])]

        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)

        if str(user.id) not in allowed_test_ids:
            return await interaction.response.send_message(
                f"❌ **SAFETY:** User {user.mention} is not on the `test_user_ids` allowlist.",
                ephemeral=True
            )

        if confirmation != user.name:
            return await interaction.response.send_message(
                f"❌ Confirmation failed. Provide username `{user.name}` to confirm.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                return await interaction.followup.send(f"❌ {user.mention} has no data to reset.")
            
            await session.delete(user_obj)
            await session.commit()
            logger.warning(f"DESTRUCTIVE: Wiped all data for test user {user} ({user.id}) on behalf of {interaction.user}.")
            await interaction.followup.send(f"✅ Wiped all data for test user {user.mention}.")
            
    @reset_group.command(name="daily", description="Reset a user's daily claim timer")
    async def reset_daily(self, interaction: discord.Interaction, user: discord.User):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                return await interaction.followup.send(f"❌ {user.mention} has no data to reset.")

            user_obj.last_daily_claim = None
            session.add(user_obj)
            await session.commit()
            logger.info(f"Daily timer for {user} ({user.id}) was reset by {interaction.user}.")
            await interaction.followup.send(f"✅ Reset the daily timer for {user.mention}. They can now use `/daily` again.")

    # --- List Commands ---
    @list_group.command(name="users", description="List the top 25 registered users by level")
    async def list_users(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            stmt = select(User).order_by(User.level.desc(), User.xp.desc()).limit(25)
            users = (await session.execute(stmt)).scalars().all()
        if not users:
            return await interaction.followup.send("❌ No users found.")
        embed = discord.Embed(title="👥 Top 25 Users by Level", color=discord.Color.green())
        description = "\n".join([
            f"`{i:2}.` **{self.bot.get_user(int(u.user_id)) or f'ID: {u.user_id}'}** - Lvl **{u.level}** ({u.xp:,} XP)"
            for i, u in enumerate(users, 1)
        ])
        embed.description = description
        await interaction.followup.send(embed=embed)

    @list_group.command(name="esprits", description="List all Esprits owned by a user")
    async def list_esprits(self, interaction: discord.Interaction, user: discord.User):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            async with get_session() as session:
                # Use a more explicit join condition for reliability
                stmt = (
                    select(UserEsprit, EspritData)
                    .join(EspritData, UserEsprit.esprit_data_id == EspritData.esprit_id)
                    .where(UserEsprit.owner_id == str(user.id))
                    .order_by(EspritData.rarity.desc(), UserEsprit.current_level.desc())
                )
                results = (await session.execute(stmt)).all()

            if not results:
                return await interaction.followup.send(f"❌ {user.mention} does not own any Esprits.")

            # The EspritPaginatorView handles the results
            view = EspritPaginatorView(interaction.user.id, user.display_name, results)
            await interaction.followup.send(embed=view.get_page_embed(), view=view)
            
        except Exception as e:
            logger.error(f"Failed to list esprits for user {user.id}:", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred while fetching the esprit list.")

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
    logger.info("✅ AdminCog loaded - Ultimate version with all features.")