# src/cogs/admin_cog.py
import logging
from contextlib import asynccontextmanager
from typing import List, Tuple, Dict

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


# --- Pagination View for Listing Esprits ---
class EspritPaginatorView(discord.ui.View):
    def __init__(self, author_id: int, user_display_name: str, all_esprits: List[Tuple[UserEsprit, EspritData]], per_page: int = 5):
        super().__init__(timeout=180)
        self.author_id, self.user_display_name, self.all_esprits, self.per_page = author_id, user_display_name, all_esprits, per_page
        self.current_page, self.total_pages = 0, (len(all_esprits) - 1) // per_page
        self.update_buttons()
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This is not your menu.", ephemeral=True); return False
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
        self.current_page -= 1; self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1; self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)


# --- Main Admin Cog ---
class AdminCog(commands.Cog):
    """Owner-only administrative slash commands for bot management."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # --- Data for the /admin help command ---
        self.admin_commands_data = {
            "give": {
                "name": "🎁 Give Commands", "emoji": "🎁", "description": "Commands for adding currency or items to a user.",
                "commands": [
                    {"name": "/give nyxies", "usage": "<user> <amount>", "desc": "Adds nyxies to a user's balance."},
                    {"name": "/give moonglow", "usage": "<user> <amount>", "desc": "Adds moonglow to a user's balance."},
                    {"name": "/give xp", "usage": "<user> <amount>", "desc": "Adds experience points to a user."},
                    {"name": "/give esprit", "usage": "<user> <esprit_name>", "desc": "Creates a new instance of an Esprit for a user."},
                ]
            },
            "remove": {
                "name": "➖ Remove Commands", "emoji": "➖", "description": "Commands for subtracting currency or items.",
                "commands": [
                    {"name": "/remove nyxies", "usage": "<user> <amount>", "desc": "Removes nyxies from a user, down to a minimum of 0."},
                    {"name": "/remove moonglow", "usage": "<user> <amount>", "desc": "Removes moonglow from a user, down to a minimum of 0."},
                    {"name": "/remove xp", "usage": "<user> <amount>", "desc": "Removes XP from a user, down to a minimum of 0."},
                    {"name": "/remove esprit", "usage": "<user> <esprit_id>", "desc": "Deletes a specific Esprit instance by its unique ID."},
                ]
            },
            "set": {
                "name": "⚙️ Set Commands", "emoji": "⚙️", "description": "Commands for setting an exact value.",
                "commands": [
                    {"name": "/set nyxies", "usage": "<user> <amount>", "desc": "Sets a user's nyxies to an exact amount."},
                    {"name": "/set moonglow", "usage": "<user> <amount>", "desc": "Sets a user's moonglow to an exact amount."},
                    {"name": "/set level", "usage": "<user> <level>", "desc": "Sets a user's level and resets their XP to 0."},
                    {"name": "/set esprit_level", "usage": "<esprit_id> <level>", "desc": "Sets a specific Esprit's level and resets its XP to 0."},
                ]
            },
            "reset": {
                "name": "♻️ Reset Commands", "emoji": "♻️", "description": "Commands for resetting data or cooldowns.",
                "commands": [
                    {"name": "/reset daily", "usage": "<user>", "desc": "Resets a user's `/daily` command cooldown."},
                    {"name": "/reset user_data", "usage": "<user> <confirmation>", "desc": "DANGEROUS: Wipes all data for a specific user."},
                    {"name": "/reset database", "usage": "<confirmation>", "desc": "EXTREMELY DANGEROUS: Wipes all users and esprits."},
                ]
            },
            "utility": {
                "name": "🛠️ Utility Commands", "emoji": "🛠️", "description": "General-purpose administrative commands.",
                "commands": [
                    {"name": "/inspect", "usage": "<user>", "desc": "Shows a detailed embed of a user's database record."},
                    {"name": "/list users", "usage": "", "desc": "Lists the top 25 users by level."},
                    {"name": "/list esprits", "usage": "<user>", "desc": "Shows a paginated list of a user's Esprit collection."},
                    {"name": "/reload config", "usage": "", "desc": "Reloads the bot's configuration files from disk."},
                    {"name": "/reload esprits", "usage": "[force]", "desc": "Reloads Esprit data from JSON. Use force=True to update existing."},
              ]
            }
        }

    # --- Helper Context Manager ---
    @asynccontextmanager
    async def _get_user_context(self, interaction: discord.Interaction, user: discord.User):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ You are not the bot owner.", ephemeral=True); yield None, None; return
        await interaction.response.defer(ephemeral=True)
        try:
            async with get_session() as session:
                user_obj = await session.get(User, str(user.id))
                if not user_obj:
                    await interaction.followup.send(f"❌ User {user.mention} has not registered."); yield None, None
                else:
                    yield session, user_obj
                    await session.commit()
        except Exception as e:
            logger.error(f"Error in user command context for '{interaction.command.name}':", exc_info=True)
            if interaction.response.is_done(): await interaction.followup.send(f"❌ An unexpected error occurred: {e}")

    # --- Command Groups ---
    admin_group = app_commands.Group(name="admin", description="Core admin and bot management commands.")
    give_group = app_commands.Group(name="give", description="Give items or currency to a user")
    remove_group = app_commands.Group(name="remove", description="Remove items or currency from a user")
    set_group = app_commands.Group(name="set", description="Set a specific value for a user or esprit")
    reset_group = app_commands.Group(name="reset", description="Reset various data")
    list_group = app_commands.Group(name="list", description="List data from the database")
    reload_group = app_commands.Group(name="reload", description="Reload bot components")

    # --- New /admin help Command ---
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

    # --- System Commands ---
    @app_commands.command(name="inspect", description="Inspect a user's complete database record")
    async def inspect(self, interaction: discord.Interaction, user: discord.User):
        # ... (Implementation is correct and unchanged)
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj: return await interaction.followup.send(f"❌ {user.mention} has no data.")
            esprit_count = (await session.execute(select(func.count(UserEsprit.id)).where(UserEsprit.owner_id == str(user.id)))).scalar_one()
        embed = discord.Embed(title=f"🔍 Inspect: {user.display_name}", color=discord.Color.nyxies())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User ID", value=f"`{user_obj.user_id}`", inline=False)
        embed.add_field(name="Level | XP", value=f"{user_obj.level} | {user_obj.xp:,}", inline=True)
        embed.add_field(name="Esprits", value=f"{esprit_count:,}", inline=True)
        embed.add_field(name="Nyxies | Moonglow", value=f"{user_obj.nyxies:,} | {user_obj.moonglow:,}", inline=True)
        embed.add_field(name="Last Daily", value=f"{discord.utils.format_dt(user_obj.last_daily_claim, 'R') if user_obj.last_daily_claim else 'Never'}", inline=False)
        embed.add_field(name="Created At", value=f"{discord.utils.format_dt(user_obj.created_at, 'F')}", inline=False)
        await interaction.followup.send(embed=embed)

    @reload_group.command(name="config", description="Reload all configuration files")
    async def reload_config(self, interaction: discord.Interaction):
        # ... (Implementation is correct and unchanged)
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        try:
            self.bot.config_manager.reload(); logger.info(f"CONFIG reloaded by owner {interaction.user}.")
            await interaction.response.send_message("✅ Configuration files reloaded.", ephemeral=True)
        except Exception as e:
            logger.error("Error reloading configs", exc_info=True)
            await interaction.response.send_message(f"❌ Could not reload configs: {e}", ephemeral=True)

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
            await interaction.followup.send(
                "❌ Could not find `data/config/esprits.json` file!", 
                ephemeral=True
            )
        except Exception as e:
            logger.error("Error reloading Esprits", exc_info=True)
            await interaction.followup.send(
                f"❌ Could not reload Esprits: {str(e)}", 
                ephemeral=True
            )

    # --- Give Commands ---
    @give_group.command(name="nyxies", description="Give nyxies to a user")
    async def give_nyxie(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if amount <= 0: await interaction.followup.send("❌ Amount must be positive."); return
            user_obj.nyxies += amount; session.add(user_obj)
            await interaction.followup.send(f"✅ Gave **{amount:,}** nyxies. New balance: **{user_obj.nyxies:,}**.")

    @give_group.command(name="moonglow", description="Give moonglow to a user")
    async def give_dust(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if amount <= 0: await interaction.followup.send("❌ Amount must be positive."); return
            user_obj.moonglow += amount; session.add(user_obj)
            await interaction.followup.send(f"✅ Gave **{amount:,}** moonglow. New balance: **{user_obj.moonglow:,}**.")

    @give_group.command(name="xp", description="Give XP to a user")
    async def give_xp(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if amount <= 0: await interaction.followup.send("❌ Amount must be positive."); return
            user_obj.xp += amount; session.add(user_obj)
            await interaction.followup.send(f"✅ Gave **{amount:,}** XP. Current XP: **{user_obj.xp:,}**.")

    @give_group.command(name="esprit", description="Give a specific Esprit to a user by name")
    async def give_esprit(self, interaction: discord.Interaction, user: discord.User, esprit_name: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            if not await session.get(User, str(user.id)): return await interaction.followup.send(f"❌ {user.mention} must use /start first.")
            stmt = select(EspritData).where(func.lower(EspritData.name) == esprit_name.lower())
            esprit_data = (await session.execute(stmt)).scalars().first()
            if not esprit_data: return await interaction.followup.send(f"❌ No Esprit definition found for `{esprit_name}`.")
            new_esprit = UserEsprit(owner_id=str(user.id), esprit_data_id=esprit_data.esprit_id, current_level=1, current_xp=0, current_hp=esprit_data.base_hp)
            session.add(new_esprit); await session.commit(); await session.refresh(new_esprit)
            await interaction.followup.send(f"✅ Gave **{esprit_data.name}** (ID: `{new_esprit.id}`) to {user.mention}.")

    # --- Remove Commands ---
    @remove_group.command(name="nyxies", description="Remove nyxies from a user")
    async def remove_nyxie(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if amount <= 0: await interaction.followup.send("❌ Amount must be positive."); return
            user_obj.nyxies = max(0, user_obj.nyxies - amount); session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** nyxies. New balance: **{user_obj.nyxies:,}**.")

    @remove_group.command(name="moonglow", description="Remove moonglow from a user")
    async def remove_dust(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if amount <= 0: await interaction.followup.send("❌ Amount must be positive."); return
            user_obj.moonglow = max(0, user_obj.moonglow - amount); session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** moonglow. New balance: **{user_obj.moonglow:,}**.")

    @remove_group.command(name="xp", description="Remove XP from a user")
    async def remove_xp(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if amount <= 0: await interaction.followup.send("❌ Amount must be positive."); return
            user_obj.xp = max(0, user_obj.xp - amount); session.add(user_obj)
            await interaction.followup.send(f"✅ Removed **{amount:,}** XP. New balance: **{user_obj.xp:,}**.")

    @remove_group.command(name="esprit", description="Remove a specific Esprit from a user by its unique ID")
    async def remove_esprit(self, interaction: discord.Interaction, user: discord.User, esprit_id: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            # The UserEsprit primary key is likely an integer if you used the default,
            # but since your IDs are UUIDs, we should query for the string version.
            # If the PK is an int, this will need adjustment, but this code assumes string/UUID PKs.
            stmt = select(UserEsprit).where(UserEsprit.id == esprit_id)
            esprit_to_remove = (await session.execute(stmt)).scalar_one_or_none()
            
            if not esprit_to_remove: return await interaction.followup.send(f"❌ No Esprit found with ID `{esprit_id}`.")
            if esprit_to_remove.owner_id != str(user.id): return await interaction.followup.send(f"❌ That Esprit does not belong to {user.mention}.")
            
            await session.delete(esprit_to_remove)
            await session.commit()
            await interaction.followup.send(f"✅ Removed Esprit ID `{esprit_id}` from {user.mention}.")

    # --- Set Commands ---
    @set_group.command(name="nyxies", description="Set a user's exact nyxies amount")
    async def set_nyxie(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if amount < 0: await interaction.followup.send("❌ Amount cannot be negative."); return
            user_obj.nyxies = amount; session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s nyxies to **{amount:,}**.")

    @set_group.command(name="moonglow", description="Set a user's exact moonglow amount")
    async def set_dust(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if amount < 0: await interaction.followup.send("❌ Amount cannot be negative."); return
            user_obj.moonglow = amount; session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s moonglow to **{amount:,}**.")

    @set_group.command(name="level", description="Set a user's level and reset their XP")
    async def set_level(self, interaction: discord.Interaction, user: discord.User, level: int):
        async with self._get_user_context(interaction, user) as (session, user_obj):
            if not session: return
            if level <= 0: await interaction.followup.send("❌ Level must be positive."); return
            user_obj.level = level; user_obj.xp = 0; session.add(user_obj)
            await interaction.followup.send(f"✅ Set {user.mention}'s level to **{level}** and reset XP to 0.")

    @set_group.command(name="esprit_level", description="Set the level for a specific Esprit instance")
    async def set_esprit_level(self, interaction: discord.Interaction, esprit_id: str, level: int):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        if level <= 0: return await interaction.response.send_message("❌ Level must be positive.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            stmt = select(UserEsprit).where(UserEsprit.id == esprit_id)
            user_esprit = (await session.execute(stmt)).scalar_one_or_none()

            if not user_esprit: return await interaction.followup.send(f"❌ No Esprit found with ID `{esprit_id}`.")
            
            user_esprit.current_level = level
            user_esprit.current_xp = 0
            session.add(user_esprit)
            await session.commit()
            await interaction.followup.send(f"✅ Set Esprit ID `{esprit_id}` to **Level {level}**.")
    
    # --- Reset Commands ---
    @reset_group.command(name="user_data", description="[DANGEROUS] Wipes all data for a specific user")
    async def reset_user_data(self, interaction: discord.Interaction, user: discord.User, confirmation: str):
        # --- Pre-computation ---
        # Load the list of test user IDs from your config
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        allowed_test_ids = [str(uid) for uid in game_settings.get("test_user_ids", [])]

        # --- Step 1: Authorization & Safety Checks ---
        # Enforce owner-only access
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)

        # NEW: Check if the target user is on the allowlist
        if str(user.id) not in allowed_test_ids:
            return await interaction.response.send_message(
                f"❌ **SAFETY:** User {user.mention} is not on the `test_user_ids` allowlist in your configuration. This command is disabled for non-test users.",
                ephemeral=True
            )

        # Enforce exact confirmation
        if confirmation != user.name:
            return await interaction.response.send_message(
                f"❌ Confirmation failed. Provide username `{user.name}` to confirm.",
                ephemeral=True
            )

        # --- Step 2: Execution ---
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                return await interaction.followup.send(f"❌ {user.mention} has no data to reset.")

            await session.delete(user_obj)
            await session.commit()
            logger.warning(f"DESTRUCTIVE: Wiped all data for test user {user} ({user.id}) on behalf of {interaction.user}.")

    # --- List Commands ---
    @list_group.command(name="users", description="List the top 25 registered users by level")
    async def list_users(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            stmt = select(User).order_by(User.level.desc(), User.xp.desc()).limit(25)
            users = (await session.execute(stmt)).scalars().all()
        if not users: return await interaction.followup.send("❌ No users found.")
        embed = discord.Embed(title="👥 Top 25 Users by Level", color=discord.Color.green())
        description = "\n".join([f"`{i:2}.` **{self.bot.get_user(int(u.user_id)) or f'ID: {u.user_id}'}** - Lvl **{u.level}** ({u.xp:,} XP)" for i, u in enumerate(users, 1)])
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

            # The EspritPaginatorView is correct and will handle the results
            view = EspritPaginatorView(interaction.user.id, user.display_name, results)
            await interaction.followup.send(embed=view.get_page_embed(), view=view)
            
        except Exception as e:
            logger.error(f"Failed to list esprits for user {user.id}:", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred while fetching the esprit list.")

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
    logger.info("✅ AdminCog loaded with final helper method pattern.")