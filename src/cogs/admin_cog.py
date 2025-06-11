# src/cogs/admin_cog.py
import logging
from contextlib import asynccontextmanager
from typing import List, Tuple, Dict, Literal
import traceback
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func
from sqlmodel import select

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ───────────────────────────────────────── UI COMPONENTS ────────────────────────────────────────── #

class AdminHelpSelect(discord.ui.Select):
    """Dropdown for selecting an admin-command category."""
    def __init__(self, command_data: Dict):
        self.command_data = command_data
        options = [
            discord.SelectOption(
                label=data["name"], description=data["description"],
                emoji=data["emoji"], value=category
            ) for category, data in command_data.items()
        ]
        super().__init__(placeholder="Select a command category to view commands…", options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        data = self.command_data[category]
        embed = discord.Embed(
            title=f"{data['emoji']} {data['name']}",
            description=data["description"], color=discord.Color.orange()
        )
        for cmd in data["commands"]:
            embed.add_field(name=f"`{cmd['name']}`", value=f"**Usage**:\t`{cmd['usage']}`\n{cmd['desc']}", inline=False)
        embed.set_footer(text="All commands are owner-only.")
        await interaction.response.edit_message(embed=embed)


class AdminHelpView(discord.ui.View):
    """View holding the admin help dropdown."""
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
    """Interactive view for navigating global-stats pages."""
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
        embed_factory = {
            "overview": self._overview_embed, "economy": self._economy_embed,
            "esprits": self._esprits_embed, "users": self._users_embed,
        }
        return embed_factory[self.current_page]()

    def _overview_embed(self) -> discord.Embed:
        embed = discord.Embed(title="📊 Nyxa Global Statistics – Overview", description="Quick overview of key metrics", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
        embed.add_field(name="🔑 Key Metrics", value=f"**Total Users:** {self.stats_data['total_users']:,}\n**Active Today:** {self.stats_data['users_claimed_today']:,}\n**Total Esprits Owned:** {self.stats_data['total_esprits_owned']:,}\n**Total Nyxies:** {self.stats_data['total_nyxies']:,}", inline=True)
        embed.add_field(name="🤖 Bot Status", value=f"**Guilds:** {self.stats_data['guild_count']:,}\n**Members:** {self.stats_data['member_count']:,}\n**Uptime:** {self.stats_data['uptime']}", inline=True)
        embed.add_field(name="📈 Quick Stats", value=f"**Avg Level:** {self.stats_data['avg_level']:.1f}\n**Collection Rate:** {self.stats_data['collection_rate']:.1f}%\n**Active (7 d):** {self.stats_data['active_users']:,}", inline=True)
        embed.set_footer(text="Click buttons below for detailed views")
        return embed

    def _economy_embed(self) -> discord.Embed:
        embed = discord.Embed(title="💰 Global Economy Statistics", description="Detailed breakdown of the in-game economy", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="💎 Currency in Circulation", value=f"**Nyxies:** {self.stats_data['total_nyxies']:,}\n**Moonglow:** {self.stats_data['total_moonglow']:,}\n**Azurites:** {self.stats_data['total_azurites']:,}\n**Azurite Shards:** {self.stats_data['total_azurite_shards']:,}\n**Essence:** {self.stats_data['total_essence']:,}\n**Loot Chests:** {self.stats_data['total_loot_chests']:,}", inline=True)
        if self.stats_data['total_users'] > 0:
            embed.add_field(name="📊 Per-User Averages", value=f"**Avg Nyxies:** {self.stats_data['total_nyxies']//self.stats_data['total_users']:,}\n**Avg Moonglow:** {self.stats_data['total_moonglow']//self.stats_data['total_users']:,}\n**Avg Azurites:** {self.stats_data['total_azurites']/self.stats_data['total_users']:.1f}\n**Avg Shards:** {self.stats_data['total_azurite_shards']/self.stats_data['total_users']:.1f}\n**Avg Loot Chests:** {self.stats_data['total_loot_chests']/self.stats_data['total_users']:.1f}", inline=True)
        return embed

    def _esprits_embed(self) -> discord.Embed:
        embed = discord.Embed(title="🔮 Esprit Collection Statistics", description="Detailed breakdown of Esprit ownership & distribution", color=discord.Color.purple(), timestamp=discord.utils.utcnow())
        embed.add_field(name="📈 Collection Overview", value=f"**Total Owned:** {self.stats_data['total_esprits_owned']:,}\n**Unique Collected:** {self.stats_data['unique_esprits_owned']}/{self.stats_data['total_esprit_types']}\n**Collection Rate:** {self.stats_data['collection_rate']:.1f}%\n**Avg per User:** {self.stats_data['total_esprits_owned']/max(1, self.stats_data['total_users']):.1f}", inline=True)
        if self.stats_data['rarity_distribution']:
            rarity_text = "\n".join(f"**{r}:** {c:,}" for r, c in sorted(self.stats_data['rarity_distribution'].items())); embed.add_field(name="🌟 Rarity Distribution", value=rarity_text or "No Esprits owned", inline=True)
        embed.add_field(name="🏆 Most Popular Esprit", value=self.stats_data['popular_esprit_name'], inline=True)
        return embed

    def _users_embed(self) -> discord.Embed:
        embed = discord.Embed(title="👥 User Statistics", description="Detailed breakdown of user activity & progression", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
        embed.add_field(name="📊 User Base", value=f"**Total Registered:** {self.stats_data['total_users']:,}\n**Active (7 d):** {self.stats_data['active_users']:,}\n**Active (Today):** {self.stats_data['users_claimed_today']:,}\n**Activity Rate:** {(self.stats_data['active_users']/max(1, self.stats_data['total_users'])*100):.1f}%", inline=True)
        embed.add_field(name="📈 Level Distribution", value=f"**Average Level:** {self.stats_data['avg_level']:.1f}\n**Highest Level:** {self.stats_data['max_level']}\n**Top Player:** {self.stats_data['top_player_mention']}", inline=True)
        embed.add_field(name="🎮 Engagement", value=f"**Daily Claim Rate:** {(self.stats_data['users_claimed_today']/max(1, self.stats_data['total_users'])*100):.1f}%\n**Avg Esprits/User:** {self.stats_data['total_esprits_owned']/max(1, self.stats_data['total_users']):.1f}\n**Total XP Earned:** {self.stats_data.get('total_xp', 0):,}", inline=True)
        return embed

    @discord.ui.button(label="Overview", style=discord.ButtonStyle.primary, emoji="📊")
    async def overview_button(self, interaction: discord.Interaction, button: discord.ui.Button): self.current_page = "overview"; await interaction.response.edit_message(embed=self.get_embed(), view=self)
    @discord.ui.button(label="Economy", style=discord.ButtonStyle.success, emoji="💰")
    async def economy_button(self, interaction: discord.Interaction, button: discord.ui.Button): self.current_page = "economy"; await interaction.response.edit_message(embed=self.get_embed(), view=self)
    @discord.ui.button(label="Esprits", style=discord.ButtonStyle.secondary, emoji="🔮")
    async def esprits_button(self, interaction: discord.Interaction, button: discord.ui.Button): self.current_page = "esprits"; await interaction.response.edit_message(embed=self.get_embed(), view=self)
    @discord.ui.button(label="Users", style=discord.ButtonStyle.secondary, emoji="👥")
    async def users_button(self, interaction: discord.Interaction, button: discord.ui.Button): self.current_page = "users"; await interaction.response.edit_message(embed=self.get_embed(), view=self)
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_message("♻️ Refreshing stats… Run `/admin stats` again.", ephemeral=True)


class EspritPaginatorView(discord.ui.View):
    def __init__(self, author_id: int, user_display_name: str, all_esprits: List[Tuple[UserEsprit, EspritData]], per_page: int = 5):
        super().__init__(timeout=180)
        self.author_id, self.user_display_name, self.all_esprits, self.per_page = author_id, user_display_name, all_esprits, per_page
        self.current_page, self.total_pages = 0, (len(all_esprits) - 1) // per_page
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id: await interaction.response.send_message("This is not your menu.", ephemeral=True); return False
        return True

    def _page_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🔮 {self.user_display_name}'s Esprit Collection", color=discord.Color.purple())
        start = self.current_page * self.per_page
        end = start + self.per_page
        embed.description = "".join(f"**{ed.name}** (ID `{ue.id}`)\n└ Lvl **{ue.current_level}** | Rarity **{ed.rarity}**\n" for ue, ed in self.all_esprits[start:end])
        embed.set_footer(text=f"Page {self.current_page+1}/{self.total_pages+1} | Total Esprits: {len(self.all_esprits)}")
        return embed

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button): self.current_page -= 1; self.update_buttons(); await interaction.response.edit_message(embed=self._page_embed(), view=self)
    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button): self.current_page += 1; self.update_buttons(); await interaction.response.edit_message(embed=self._page_embed(), view=self)

# ────────────────────────────────────────── MAIN ADMIN COG ───────────────────────────────────────── #
@app_commands.guild_only()
class AdminCog(commands.Cog):
    MODIFIABLE_ATTRIBUTES = ('nyxies', 'moonglow', 'azurites', 'azurite_shards', 'essence', 'xp', 'loot_chests')

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.admin_commands_data = {"give":{"name":"🎁 Give Commands","emoji":"🎁","description":"Commands for adding currency or items to a user.","commands":[{"name":"/give nyxies","usage":"<user> <amount>","desc":"Adds nyxies to a user's balance."},{"name":"/give moonglow","usage":"<user> <amount>","desc":"Adds moonglow to a user's balance."},{"name":"/give azurites","usage":"<user> <amount>","desc":"Adds whole azurites to a user's balance."},{"name":"/give azurite_shards","usage":"<user> <amount>","desc":"Adds azurite shards to a user's balance."},{"name":"/give essence","usage":"<user> <amount>","desc":"Adds essence to a user's balance."},{"name":"/give xp","usage":"<user> <amount>","desc":"Adds experience points to a user."},{"name":"/give loot_chests","usage":"<user> <amount>","desc":"Adds loot chests to a user."},{"name":"/give esprit","usage":"<user> <esprit_name>","desc":"Creates a new instance of an Esprit for a user."}]},"remove":{"name":"➖ Remove Commands","emoji":"➖","description":"Commands for subtracting currency or items.","commands":[{"name":"/remove nyxies","usage":"<user> <amount>","desc":"Removes nyxies from a user, down to a minimum of 0."},{"name":"/remove moonglow","usage":"<user> <amount>","desc":"Removes moonglow from a user, down to a minimum of 0."},{"name":"/remove azurites","usage":"<user> <amount>","desc":"Removes azurites from a user, down to a minimum of 0."},{"name":"/remove azurite_shards","usage":"<user> <amount>","desc":"Removes azurite shards from a user, down to a minimum of 0."},{"name":"/remove essence","usage":"<user> <amount>","desc":"Removes essence from a user, down to a minimum of 0."},{"name":"/remove xp","usage":"<user> <amount>","desc":"Removes XP from a user, down to a minimum of 0."},{"name":"/remove loot_chests","usage":"<user> <amount>","desc":"Removes loot chests from a user, down to a minimum of 0."},{"name":"/remove esprit","usage":"<user> <esprit_id>","desc":"Deletes a specific Esprit instance by its unique ID."}]},"set":{"name":"⚙️ Set Commands","emoji":"⚙️","description":"Commands for setting an exact value.","commands":[{"name":"/set nyxies","usage":"<user> <amount>","desc":"Sets a user's nyxies to an exact amount."},{"name":"/set moonglow","usage":"<user> <amount>","desc":"Sets a user's moonglow to an exact amount."},{"name":"/set azurites","usage":"<user> <amount>","desc":"Sets a user's azurites to an exact amount."},{"name":"/set azurite_shards","usage":"<user> <amount>","desc":"Sets a user's azurite shards to an exact amount."},{"name":"/set essence","usage":"<user> <amount>","desc":"Sets a user's essence to an exact amount."},{"name":"/set loot_chests","usage":"<user> <amount>","desc":"Sets a user's loot chests to an exact amount."},{"name":"/set level","usage":"<user> <level>","desc":"Sets a user's level and resets their XP to 0."},{"name":"/set esprit_level","usage":"<esprit_id> <level>","desc":"Sets a specific Esprit's level and resets its XP to 0."}]},"reset":{"name":"♻️ Reset Commands","emoji":"♻️","description":"Commands for resetting data or cooldowns.","commands":[{"name":"/reset daily","usage":"<user>","desc":"Resets a user's `/daily` command cooldown."},{"name":"/reset user_data","usage":"<user> <confirmation>","desc":"DANGEROUS: Wipes all data for a specific user."}]},"utility":{"name":"🛠️ Utility Commands","emoji":"🛠️","description":"General-purpose administrative commands.","commands":[{"name":"/admin stats","usage":"","desc":"Shows comprehensive global stats."},{"name":"/inspect","usage":"<user>","desc":"Shows a detailed embed of a user's DB record."},{"name":"/list users","usage":"","desc":"Lists the top 25 users by level."},{"name":"/list esprits","usage":"<user>","desc":"Shows a paginated list of a user's Esprit collection."},{"name":"/reload config","usage":"","desc":"Reloads the bot's configuration files from disk."},{"name":"/reload esprits","usage":"[force]","desc":"Reloads Esprit data from JSON."},{"name":"/reload cog","usage":"<cog_name>","desc":"Reloads a specific bot cog."}]}}

    @asynccontextmanager
    async def _get_user_context(self, interaction: discord.Interaction, user: discord.User):
        if not await self.bot.is_owner(interaction.user): await interaction.response.send_message("❌ You are not the bot owner.", ephemeral=True); yield None, None; return
        await interaction.response.defer(ephemeral=True)
        try:
            async with get_session() as session:
                user_obj = await session.get(User, str(user.id))
                if not user_obj: await interaction.followup.send(f"❌ User {user.mention} has not registered."); yield None, None
                else: yield session, user_obj; await session.commit()
        except Exception as exc:
            logger.error("User context error:", exc_info=True)
            if interaction.response.is_done(): await interaction.followup.send(f"❌ Unexpected error: {exc}")
            yield None, None

    async def _adjust_user_attribute(self, interaction: discord.Interaction, user: discord.User, attribute: str, operation: Literal['give', 'remove', 'set'], amount: int):
        if attribute not in self.MODIFIABLE_ATTRIBUTES: logger.error(f"Invalid attribute '{attribute}'"); return await interaction.response.send_message("Internal error.", ephemeral=True)
        if amount < 0 and operation != 'set': return await interaction.response.send_message("❌ Amount must be non-negative.", ephemeral=True)
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            current_val, verb = getattr(user_obj, attribute), {"give": "Gave", "remove": "Removed", "set": "Set"}[operation]
            if operation == "give": new_val = current_val + amount
            elif operation == "remove": new_val = max(0, current_val - amount)
            else: new_val = amount
            setattr(user_obj, attribute, new_val); session.add(user_obj)
            display = attribute.replace('_', ' ').title()
            msg = (f"✅ {verb} {user.mention}'s {display} to **{new_val:,}**." if operation == "set" else f"✅ {verb} **{amount:,}** {display}. New balance **{new_val:,}**.")
            await interaction.followup.send(msg); logger.info(f"{verb} {amount} {attribute} for user {user.id} ({interaction.user})")

    admin_group  = app_commands.Group(name="admin",  description="Core admin commands.")
    give_group   = app_commands.Group(name="give",   description="Give currency/items")
    remove_group = app_commands.Group(name="remove", description="Remove currency/items")
    set_group    = app_commands.Group(name="set",    description="Set exact values")
    reset_group  = app_commands.Group(name="reset",  description="Reset data/cooldowns")
    list_group   = app_commands.Group(name="list",   description="List data from DB")
    reload_group = app_commands.Group(name="reload", description="Reload bot components")

    @admin_group.command(name="help", description="Interactive admin manual")
    async def help(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ You are not the bot owner.", ephemeral=True)
        embed = discord.Embed(title="🛠️ Nyxa Admin Command Center", description="Select a category from the dropdown to view commands & usage.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, view=AdminHelpView(interaction.user.id, self.admin_commands_data), ephemeral=True)

    @admin_group.command(name="stats", description="Display global bot statistics")
    async def global_stats(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        stats = {}
        try:
            async with get_session() as session:
                stats['total_users'] = (await session.execute(select(func.count(User.user_id)))).scalar_one() or 0
                stats['avg_level'] = (await session.execute(select(func.avg(User.level)))).scalar_one() or 0
                stats['total_xp'] = (await session.execute(select(func.sum(User.xp)))).scalar_one() or 0
                max_user_result = (await session.execute(select(User).order_by(User.level.desc()).limit(1))).scalar_one_or_none()
                if max_user_result:
                    stats['max_level'] = max_user_result.level
                    top_user = self.bot.get_user(int(max_user_result.user_id))
                    stats['top_player_mention'] = top_user.mention if top_user else f"ID {max_user_result.user_id}"
                else:
                    stats['max_level'], stats['top_player_mention'] = 0, "None"
                stats['total_nyxies'] = (await session.execute(select(func.sum(User.nyxies)))).scalar_one() or 0
                stats['total_moonglow'] = (await session.execute(select(func.sum(User.moonglow)))).scalar_one() or 0
                stats['total_azurites'] = (await session.execute(select(func.sum(User.azurites)))).scalar_one() or 0
                stats['total_azurite_shards'] = (await session.execute(select(func.sum(User.azurite_shards)))).scalar_one() or 0
                stats['total_essence'] = (await session.execute(select(func.sum(User.essence)))).scalar_one() or 0
                stats['total_loot_chests'] = (await session.execute(select(func.sum(User.loot_chests)))).scalar_one() or 0
                stats['total_esprits_owned'] = (await session.execute(select(func.count(UserEsprit.id)))).scalar_one() or 0
                stats['unique_esprits_owned'] = (await session.execute(select(func.count(func.distinct(UserEsprit.esprit_data_id))))).scalar_one() or 0
                stats['total_esprit_types'] = (await session.execute(select(func.count(EspritData.esprit_id)))).scalar_one() or 1
                stats['collection_rate'] = stats['unique_esprits_owned'] / max(1, stats['total_esprit_types']) * 100
                popular_result = (await session.execute(select(UserEsprit.esprit_data_id, func.count(UserEsprit.id).label('cnt')).group_by(UserEsprit.esprit_data_id).order_by(func.count(UserEsprit.id).desc()).limit(1))).first()
                if popular_result:
                    esprit_data = await session.get(EspritData, popular_result[0])
                    stats['popular_esprit_name'] = f"{esprit_data.name} ({popular_result[1]} owned)" if esprit_data else "Unknown"
                else:
                    stats['popular_esprit_name'] = "None yet"
                stats['rarity_distribution'] = dict((await session.execute(select(EspritData.rarity, func.count(UserEsprit.id)).join(UserEsprit, UserEsprit.esprit_data_id == EspritData.esprit_id).group_by(EspritData.rarity))).all())
                today_cutoff, week_cutoff = datetime.utcnow().date(), datetime.utcnow() - timedelta(days=7)
                stats['users_claimed_today'] = (await session.execute(select(func.count(User.user_id)).where(User.last_daily_claim != None).where(func.date(User.last_daily_claim) == today_cutoff))).scalar_one() or 0
                stats['active_users'] = (await session.execute(select(func.count(User.user_id)).where(User.last_daily_claim >= week_cutoff))).scalar_one() or 0
            stats['guild_count'], stats['member_count'] = len(self.bot.guilds), sum(g.member_count for g in self.bot.guilds if g.member_count)
            stats['uptime'] = discord.utils.format_dt(getattr(self.bot, 'start_time', discord.utils.utcnow()), 'R')
            view = StatsView(stats, interaction.user.id)
            await interaction.followup.send(embed=view.get_embed(), view=view)
        except Exception as exc:
            logger.error("Error generating stats:", exc_info=True)
            await interaction.followup.send(f"❌ Error: {exc}", ephemeral=True)

    @app_commands.command(name="inspect", description="Inspect a user's complete DB record")
    async def inspect(self, interaction: discord.Interaction, user: discord.User):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj: return await interaction.followup.send(f"❌ {user.mention} has no data.")
            esprit_count = (await session.execute(select(func.count(UserEsprit.id)).where(UserEsprit.owner_id == str(user.id)))).scalar_one()
        embed = discord.Embed(title=f"🔍 Inspect: {user.display_name}", color=discord.Color.gold()); embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User ID", value=f"`{user_obj.user_id}`", inline=False)
        embed.add_field(name="Level | XP", value=f"{user_obj.level} | {user_obj.xp:,}", inline=True); embed.add_field(name="Esprits", value=f"{esprit_count:,}", inline=True)
        embed.add_field(name="Nyxies | Moonglow", value=f"{user_obj.nyxies:,} | {user_obj.moonglow:,}", inline=True)
        embed.add_field(name="Azurites", value=f"{user_obj.azurites:,}", inline=True); embed.add_field(name="Azurite Shards", value=f"{user_obj.azurite_shards:,}", inline=True)
        embed.add_field(name="Essence", value=f"{user_obj.essence:,}", inline=True); embed.add_field(name="Loot Chests", value=f"{user_obj.loot_chests:,}", inline=True)
        embed.add_field(name="Last Daily", value=discord.utils.format_dt(user_obj.last_daily_claim, 'R') if user_obj.last_daily_claim else "Never", inline=False)
        embed.add_field(name="Created At", value=discord.utils.format_dt(user_obj.created_at, 'F'), inline=False)
        await interaction.followup.send(embed=embed)

    @give_group.command(name="nyxies", description="Give nyxies")
    async def give_nyxies(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'nyxies', 'give', a)
    @give_group.command(name="moonglow", description="Give moonglow")
    async def give_moonglow(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'moonglow', 'give', a)
    @give_group.command(name="azurites", description="Give azurites")
    async def give_azurites(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'azurites', 'give', a)
    @give_group.command(name="azurite_shards", description="Give azurite_shards")
    async def give_azurite_shards(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'azurite_shards', 'give', a)
    @give_group.command(name="essence", description="Give essence")
    async def give_essence(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'essence', 'give', a)
    @give_group.command(name="xp", description="Give xp")
    async def give_xp(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'xp', 'give', a)
    @give_group.command(name="loot_chests", description="Give loot_chests")
    async def give_loot_chests(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'loot_chests', 'give', a)
    @give_group.command(name="esprit", description="Give a specific Esprit to a user by name")
    async def give_esprit(self, interaction: discord.Interaction, user: discord.User, esprit_name: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            if not await session.get(User, str(user.id)): return await interaction.followup.send(f"❌ {user.mention} must `/start` first.")
            esprit_data = (await session.execute(select(EspritData).where(func.lower(EspritData.name) == esprit_name.lower()))).scalars().first()
            if not esprit_data: return await interaction.followup.send(f"❌ No Esprit named `{esprit_name}`.")
            user_esprit = UserEsprit(owner_id=str(user.id), esprit_data_id=esprit_data.esprit_id, current_level=1, current_xp=0, current_hp=esprit_data.base_hp)
            session.add(user_esprit); await session.commit(); await session.refresh(user_esprit)
            await interaction.followup.send(f"✅ Gave **{esprit_data.name}** (ID `{user_esprit.id}`) to {user.mention}.")

    @remove_group.command(name="nyxies", description="Remove nyxies")
    async def remove_nyxies(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'nyxies', 'remove', a)
    @remove_group.command(name="moonglow", description="Remove moonglow")
    async def remove_moonglow(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'moonglow', 'remove', a)
    @remove_group.command(name="azurites", description="Remove azurites")
    async def remove_azurites(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'azurites', 'remove', a)
    @remove_group.command(name="azurite_shards", description="Remove azurite_shards")
    async def remove_azurite_shards(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'azurite_shards', 'remove', a)
    @remove_group.command(name="essence", description="Remove essence")
    async def remove_essence(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'essence', 'remove', a)
    @remove_group.command(name="xp", description="Remove xp")
    async def remove_xp(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'xp', 'remove', a)
    @remove_group.command(name="loot_chests", description="Remove loot_chests")
    async def remove_loot_chests(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'loot_chests', 'remove', a)
    @remove_group.command(name="esprit", description="Remove a specific Esprit by its ID")
    async def remove_esprit(self, interaction: discord.Interaction, user: discord.User, esprit_id: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_esprit = (await session.execute(select(UserEsprit).where(UserEsprit.id == esprit_id))).scalar_one_or_none()
            if not user_esprit: return await interaction.followup.send(f"❌ No Esprit with ID `{esprit_id}`.")
            if user_esprit.owner_id != str(user.id): return await interaction.followup.send("❌ That Esprit does not belong to that user.")
            await session.delete(user_esprit); await session.commit()
            await interaction.followup.send(f"✅ Removed Esprit ID `{esprit_id}` from {user.mention}.")

    @set_group.command(name="nyxies", description="Set nyxies")
    async def set_nyxies(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'nyxies', 'set', a)
    @set_group.command(name="moonglow", description="Set moonglow")
    async def set_moonglow(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'moonglow', 'set', a)
    @set_group.command(name="azurites", description="Set azurites")
    async def set_azurites(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'azurites', 'set', a)
    @set_group.command(name="azurite_shards", description="Set azurite_shards")
    async def set_azurite_shards(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'azurite_shards', 'set', a)
    @set_group.command(name="essence", description="Set essence")
    async def set_essence(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'essence', 'set', a)
    @set_group.command(name="xp", description="Set xp")
    async def set_xp(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'xp', 'set', a)
    @set_group.command(name="loot_chests", description="Set loot_chests")
    async def set_loot_chests(self, i: discord.Interaction, u: discord.User, a: int): await self._adjust_user_attribute(i, u, 'loot_chests', 'set', a)
    @set_group.command(name="level", description="Set a user's level (resets XP)")
    async def set_level(self, interaction: discord.Interaction, user: discord.User, level: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if level <= 0: return await interaction.followup.send("❌ Level must be positive.")
            user_obj.level, user_obj.xp = level, 0; session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s level to **{level}** and reset XP.")
    @set_group.command(name="esprit_level", description="Set an Esprit instance's level (resets its XP)")
    async def set_esprit_level(self, interaction: discord.Interaction, esprit_id: str, level: int):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        if level <= 0: return await interaction.response.send_message("❌ Level must be positive.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_esprit = (await session.execute(select(UserEsprit).where(UserEsprit.id == esprit_id))).scalar_one_or_none()
            if not user_esprit: return await interaction.followup.send(f"❌ No Esprit ID `{esprit_id}`.")
            user_esprit.current_level, user_esprit.current_xp = level, 0; session.add(user_esprit); await session.commit()
            await interaction.followup.send(f"✅ Set Esprit ID `{esprit_id}` to **Level {level}**.")

    @reset_group.command(name="user_data", description="Wipe all data for a *test* user")
    async def reset_user_data(self, interaction: discord.Interaction, user: discord.User, confirmation: str):
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        allowed = [str(uid) for uid in game_settings.get("developer", {}).get("test_user_ids", [])]
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        if str(user.id) not in allowed: return await interaction.response.send_message(f"❌ **SAFETY:** User {user.mention} not in `test_user_ids` allowlist.", ephemeral=True)
        if confirmation != user.name: return await interaction.response.send_message(f"❌ Confirmation failed. Type `{user.name}` exactly.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj: return await interaction.followup.send(f"❌ {user.mention} has no data.")
            await session.delete(user_obj); await session.commit()
            logger.warning("All data wiped for test user %s (%s) by %s", user, user.id, interaction.user)
            await interaction.followup.send(f"✅ Wiped all data for {user.mention}.")

    @reset_group.command(name="daily", description="Reset a user's /daily timer")
    async def reset_daily(self, interaction: discord.Interaction, user: discord.User):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            user_obj.last_daily_claim = None; session.add(user_obj)
            await interaction.followup.send(f"✅ Reset `/daily` for {user.mention}.")

    @list_group.command(name="users", description="List top 25 users by level")
    async def list_users(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            users = (await session.execute(select(User).order_by(User.level.desc(), User.xp.desc()).limit(25))).scalars().all()
        if not users: return await interaction.followup.send("❌ No users found.")
        embed = discord.Embed(title="👥 Top 25 Users by Level", color=discord.Color.green())
        embed.description = "\n".join(f"`{idx:2}.` **{self.bot.get_user(int(u.user_id)) or f'ID {u.user_id}'}** — Lvl **{u.level}** ({u.xp:,} XP)" for idx, u in enumerate(users, 1))
        await interaction.followup.send(embed=embed)

    @list_group.command(name="esprits", description="List all Esprits owned by a user")
    async def list_esprits(self, interaction: discord.Interaction, user: discord.User):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            async with get_session() as session:
                results = (await session.execute(select(UserEsprit, EspritData).join(EspritData, UserEsprit.esprit_data_id == EspritData.esprit_id).where(UserEsprit.owner_id == str(user.id)).order_by(EspritData.rarity.desc(), UserEsprit.current_level.desc()))).all()
            if not results: return await interaction.followup.send(f"❌ {user.mention} owns no Esprits.")
            view = EspritPaginatorView(interaction.user.id, user.display_name, results)
            await interaction.followup.send(embed=view._page_embed(), view=view)
        except Exception: logger.error("List esprits failed:", exc_info=True); await interaction.followup.send("❌ Failed to fetch esprits.")

    @reload_group.command(name="config", description="Reload all configuration files")
    async def reload_config(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        try:
            self.bot.config_manager.reload()
            logger.info("Config reloaded by %s", interaction.user)
            await interaction.response.send_message("✅ Configuration reloaded.", ephemeral=True)
        except Exception as exc: logger.error("Config reload failed", exc_info=True); await interaction.response.send_message(f"❌ Reload failed: {exc}", ephemeral=True)

    @reload_group.command(name="cog", description="Reload a specific cog")
    @app_commands.describe(cog_name="Module path, e.g. src.cogs.economy_cog")
    async def reload_cog(self, interaction: discord.Interaction, cog_name: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(cog_name)
            logger.info("Cog '%s' reloaded by %s", cog_name, interaction.user)
            await interaction.followup.send(f"✅ Reloaded `{cog_name}`.")
        except Exception: await interaction.followup.send(f"❌ Error reloading `{cog_name}`:\n```py\n{traceback.format_exc()[:1900]}\n```")

    @reload_group.command(name="esprits", description="Reload Esprit data from JSON")
    async def reload_esprits(self, interaction: discord.Interaction, force: bool = False):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            from src.database.data_loader import EspritDataLoader
            loader = EspritDataLoader()
            count = await loader.load_esprits(force_reload=force)
            embed = discord.Embed(title="✅ Esprit Data Reloaded", description=f"Successfully loaded **{count:,}** Esprits from JSON.", color=discord.Color.green())
            embed.add_field(name="Mode", value="Force reload (updated existing)" if force else "Normal (new entries only)", inline=False)
            missing = await loader.verify_data_integrity()
            if missing: embed.add_field(name="⚠️ Warning", value=f"{len(missing)} Esprits present in JSON but missing in DB", inline=False)
            logger.info("Esprits reloaded by %s. Count=%d Force=%s", interaction.user, count, force)
            await interaction.followup.send(embed=embed)
        except FileNotFoundError: await interaction.followup.send("❌ `data/config/esprits.json` not found!", ephemeral=True)
        except Exception as exc: logger.error("Esprits reload error", exc_info=True); await interaction.followup.send(f"❌ Reload failed: {exc}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
    logger.info("✅ AdminCog loaded - explicit version.")