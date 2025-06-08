# src/cogs/admin_cog.py
import logging
import discord
from discord.ext import commands
from discord import app_commands
from sqlmodel import delete, select
from sqlalchemy import func

from src.database.db import get_session, create_db_and_tables, populate_static_data
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger

logger = get_logger(__name__)

class AdminCog(commands.Cog):
    """Cog for owner-only administrative slash commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    # -------------------------------------------------------------------------
    # SYSTEM & DATABASE
    # -------------------------------------------------------------------------
    @app_commands.command(name="reload_configs", description="(Admin-Only) Reloads all JSON configuration files.")
    async def reload_configs(self, interaction: discord.Interaction):
        """Forces the ConfigManager to clear its cache and reload from JSON files."""
        await interaction.response.defer(ephemeral=True)
        try:
            self.bot.config_manager.reload()
            await interaction.followup.send("✅ All configuration files have been reloaded.", ephemeral=True)
            logger.info(f"Admin {interaction.user.name} reloaded all configs.")
        except Exception as e:
            logger.error(f"Error reloading configs: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while reloading configs.", ephemeral=True)

    @app_commands.command(name="reset_db", description="(OWNER-ONLY) Wipes and re-seeds the entire database. DESTRUCTIVE.")
    async def reset_db(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            async with get_session() as session:
                await session.execute(delete(UserEsprit))
                await session.execute(delete(User))
                await session.execute(delete(EspritData))
                await session.commit()
            await create_db_and_tables()
            await populate_static_data(self.bot.config_manager)
            await interaction.followup.send("✅ Database has been wiped and re-seeded.", ephemeral=True)
            logger.warning(f"/reset_db called by {interaction.user.name}")
        except Exception as e:
            logger.error(f"Error in /reset_db: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while resetting the database.", ephemeral=True)

    # -------------------------------------------------------------------------
    # USER & ESPRIT DATA
    # -------------------------------------------------------------------------
    @app_commands.command(name="inspect_user", description="(Admin-Only) Shows the raw database record for a user.")
    @app_commands.describe(user="The user to inspect.")
    async def inspect_user(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** has no data.", ephemeral=True)
                return
            
            stmt = select(func.count(UserEsprit.id)).where(UserEsprit.owner_id == str(user.id))
            owned_esprits_count = (await session.execute(stmt)).scalar_one()

            embed = discord.Embed(title=f"🔍 Inspecting: {user_obj.username}", color=discord.Color.yellow())
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="User ID", value=f"`{user_obj.user_id}`", inline=False)
            embed.add_field(name="Level", value=str(user_obj.level), inline=True)
            embed.add_field(name="XP", value=str(user_obj.xp), inline=True)
            embed.add_field(name="Owned Esprits", value=str(owned_esprits_count), inline=True)
            embed.add_field(name="Gold", value=f"{user_obj.gold:,}", inline=True)
            embed.add_field(name="Dust", value=f"{user_obj.dust:,}", inline=True)
            embed.add_field(name="Active Esprit ID", value=f"`{user_obj.active_esprit_id}`", inline=False)
            embed.add_field(name="Last Daily Claim (UTC)", value=str(user_obj.last_daily_claim), inline=False)
            embed.add_field(name="Account Created (UTC)", value=str(user_obj.created_at), inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="reset_user", description="(Admin-Only) Wipes all data for a specific user.")
    @app_commands.describe(user="The user whose account will be wiped.")
    async def reset_user(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** has no data to reset.", ephemeral=True)
                return
            
            await session.delete(user_obj)
            await session.commit()
            
            logger.warning(f"Admin {interaction.user.name} wiped all data for user {user.name}.")
            await interaction.followup.send(f"✅ All data for **{user.display_name}** has been wiped.", ephemeral=True)

    @app_commands.command(name="reset_daily", description="(Admin-Only) Resets the daily cooldown for a user.")
    @app_commands.describe(user="The user whose daily cooldown to reset.")
    async def reset_daily(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** is not registered.", ephemeral=True)
                return
            
            user_obj.last_daily_claim = None
            session.add(user_obj)
            await session.commit()
            
            logger.info(f"Admin {interaction.user.name} reset the daily cooldown for {user.name}.")
            await interaction.followup.send(f"✅ Daily cooldown for **{user.display_name}** has been reset.", ephemeral=True)

    # -------------------------------------------------------------------------
    # PROGRESSION & LEVELING
    # -------------------------------------------------------------------------
    @app_commands.command(name="set_level", description="(Admin-Only) Sets a user's level and resets their XP for that level.")
    @app_commands.describe(user="The user to modify.", level="The target level.")
    async def set_level(self, interaction: discord.Interaction, user: discord.User, level: app_commands.Range[int, 1]):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** must use `/start` first.", ephemeral=True)
                return
            user_obj.level = level
            user_obj.xp = 0
            session.add(user_obj)
            await session.commit()
            logger.info(f"Admin {interaction.user.name} set user {user.name}'s level to {level}.")
            await interaction.followup.send(f"✅ Set **{user.display_name}**'s level to **{level}** (XP reset to 0).", ephemeral=True)

    @app_commands.command(name="give_xp", description="(Admin-Only) Gives a user a specified amount of XP.")
    @app_commands.describe(user="The user to give XP to.", amount="The amount of XP to give.")
    async def give_xp(self, interaction: discord.Interaction, user: discord.User, amount: app_commands.Range[int, 1]):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** must use `/start` first.", ephemeral=True)
                return
            user_obj.xp += amount
            session.add(user_obj)
            await session.commit()
            logger.info(f"Admin {interaction.user.name} gave {amount} XP to {user.name}.")
            await interaction.followup.send(f"✅ Gave **{amount:,} XP** to **{user.display_name}**. New XP: `{user_obj.xp:,}`.", ephemeral=True)

    @app_commands.command(name="set_esprit_level", description="(Admin-Only) Sets the level for a specific Esprit instance.")
    @app_commands.describe(esprit_id="The unique ID of the Esprit.", level="The target level.")
    async def set_esprit_level(self, interaction: discord.Interaction, esprit_id: str, level: app_commands.Range[int, 1]):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_esprit = await session.get(UserEsprit, esprit_id)
            if not user_esprit:
                await interaction.followup.send(f"❌ No Esprit found with ID `{esprit_id}`.", ephemeral=True)
                return
            
            user_esprit.current_level = level
            user_esprit.current_xp = 0
            session.add(user_esprit)
            await session.commit()
            
            esprit_data = await session.get(EspritData, user_esprit.esprit_data_id)
            esprit_name = esprit_data.name if esprit_data else "Unknown Esprit"

            logger.info(f"Admin {interaction.user.name} set Esprit {esprit_name} (`{esprit_id}`) to level {level}.")
            await interaction.followup.send(f"✅ Set Esprit **{esprit_name}** (`{esprit_id}`) to level **{level}**.", ephemeral=True)

    @app_commands.command(name="set_limit_break", description="(Admin-Only) Sets the Limit Break tier for a specific Esprit.")
    @app_commands.describe(esprit_id="The unique ID of the Esprit.", tier="The target Limit Break tier.")
    async def set_limit_break(self, interaction: discord.Interaction, esprit_id: str, tier: app_commands.Range[int, 0]):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_esprit = await session.get(UserEsprit, esprit_id)
            if not user_esprit:
                await interaction.followup.send(f"❌ No Esprit found with ID `{esprit_id}`.", ephemeral=True)
                return
            
            if not hasattr(user_esprit, "limit_break_tier"):
                await interaction.followup.send("❌ The `limit_break_tier` feature is not yet in the database schema.", ephemeral=True)
                return

            user_esprit.limit_break_tier = tier
            session.add(user_esprit)
            await session.commit()
            
            esprit_data = await session.get(EspritData, user_esprit.esprit_data_id)
            esprit_name = esprit_data.name if esprit_data else "Unknown Esprit"
            
            logger.info(f"Admin {interaction.user.name} set Esprit {esprit_name} (`{esprit_id}`) to Limit Break Tier {tier}.")
            await interaction.followup.send(f"✅ Set Esprit **{esprit_name}** (`{esprit_id}`) to Limit Break Tier **{tier}**.", ephemeral=True)
            
    # -------------------------------------------------------------------------
    # ITEM & CURRENCY
    # -------------------------------------------------------------------------
    @app_commands.command(name="give_esprit", description="(Admin-Only) Gives you a specific Esprit by name.")
    @app_commands.describe(name="The exact name of the Esprit to give (case-insensitive).")
    async def give_esprit(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            stmt = select(EspritData).where(func.lower(EspritData.name) == name.lower())
            result = await session.execute(stmt)
            esprit_to_give = result.scalar_one_or_none()
            if not esprit_to_give:
                await interaction.followup.send(f"❌ Could not find an Esprit named `{name}`.", ephemeral=True)
                return
            new_user_esprit = UserEsprit(owner_id=str(interaction.user.id), esprit_data_id=esprit_to_give.esprit_id, current_hp=esprit_to_give.base_hp, current_level=1, current_xp=0)
            session.add(new_user_esprit)
            await session.commit()
            logger.info(f"Admin {interaction.user.name} gave themselves Esprit: {esprit_to_give.name}")
            await interaction.followup.send(f"✅ You have been given **{esprit_to_give.name}**.", ephemeral=True)

    @app_commands.command(name="give_gold", description="(Admin-Only) Gives a user a specified amount of gold.")
    @app_commands.describe(user="The user to give gold to.", amount="The amount of gold to give.")
    async def give_gold(self, interaction: discord.Interaction, user: discord.User, amount: app_commands.Range[int, 1]):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** must use `/start` first.", ephemeral=True)
                return
            user_obj.gold += amount
            session.add(user_obj)
            await session.commit()
            logger.info(f"Admin {interaction.user.name} gave {amount} gold to {user.name}.")
            await interaction.followup.send(f"✅ Gave **{amount:,} gold** to **{user.display_name}**. New balance: `{user_obj.gold:,}`", ephemeral=True)

    @app_commands.command(name="remove_gold", description="(Admin-Only) Removes a specified amount of gold from a user.")
    @app_commands.describe(user="The user to remove gold from.", amount="The amount of gold to remove.")
    async def remove_gold(self, interaction: discord.Interaction, user: discord.User, amount: app_commands.Range[int, 1]):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** must use `/start` first.", ephemeral=True)
                return
            original_balance = user_obj.gold
            user_obj.gold = max(0, original_balance - amount)
            removed_amount = original_balance - user_obj.gold
            session.add(user_obj)
            await session.commit()
            logger.info(f"Admin {interaction.user.name} removed {removed_amount} gold from {user.name}.")
            await interaction.followup.send(f"✅ Removed **{removed_amount:,} gold** from **{user.display_name}**. New balance: `{user_obj.gold:,}`", ephemeral=True)

    @app_commands.command(name="give_dust", description="(Admin-Only) Gives a user a specified amount of dust.")
    @app_commands.describe(user="The user to give dust to.", amount="The amount of dust to give.")
    async def give_dust(self, interaction: discord.Interaction, user: discord.User, amount: app_commands.Range[int, 1]):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** must use `/start` first.", ephemeral=True)
                return
            user_obj.dust += amount
            session.add(user_obj)
            await session.commit()
            logger.info(f"Admin {interaction.user.name} gave {amount} dust to {user.name}.")
            await interaction.followup.send(f"✅ Gave **{amount:,} dust** to **{user.display_name}**. New balance: `{user_obj.dust:,}`", ephemeral=True)

    @app_commands.command(name="remove_dust", description="(Admin-Only) Removes a specified amount of dust from a user.")
    @app_commands.describe(user="The user to remove dust from.", amount="The amount of dust to remove.")
    async def remove_dust(self, interaction: discord.Interaction, user: discord.User, amount: app_commands.Range[int, 1]):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user_obj = await session.get(User, str(user.id))
            if not user_obj:
                await interaction.followup.send(f"❌ User **{user.display_name}** must use `/start` first.", ephemeral=True)
                return
            original_balance = user_obj.dust
            user_obj.dust = max(0, original_balance - amount)
            removed_amount = original_balance - user_obj.dust
            session.add(user_obj)
            await session.commit()
            logger.info(f"Admin {interaction.user.name} removed {removed_amount} dust from {user.name}.")
            await interaction.followup.send(f"✅ Removed **{removed_amount:,} dust** from **{user.display_name}**. New balance: `{user_obj.dust:,}`", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))