# src/cogs/utility_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.database.db import get_session
from src.database.models import User, UserEsprit
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiter
from src.utils.progression_manager import ProgressionManager # Correctly import the class

import random

logger = get_logger(__name__)

FLAVOR_QUOTES = [
    "The Faye stirs. Will you answer the call?",
    "Remember: fortune favors the persistent.",
    "Pro tip: Limit breaks are the path to greatness.",
    "Did you know? Remna is the key to transcending limits.",
    "Every esprit has a destiny. Will yours awaken?",
]

class UtilityCog(commands.Cog, name="Utility"):
    """Informational and utility commands for players."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.limiter = RateLimiter(calls=5, period=20)
        # --- FIX: Create an instance of the ProgressionManager ---
        self.prog_manager = ProgressionManager(self.bot.config_manager)

    async def check_rate_limit(self, interaction: discord.Interaction) -> bool:
        if not await self.limiter.check(str(interaction.user.id)):
            wait = await self.limiter.get_cooldown(str(interaction.user.id)) or 10
            # Use followup if the interaction is already deferred
            if interaction.response.is_done():
                await interaction.followup.send(f"You're using commands too quickly! Please wait {wait}s.")
            else:
                await interaction.response.send_message(f"You're using commands too quickly! Please wait {wait}s.")
            return False
        return True

    @app_commands.command(name="profile", description="View your complete player profile and active team.")
    async def profile(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            if not await self.check_rate_limit(interaction):
                return

            async with get_session() as session:
                user = await session.get(User, str(interaction.user.id))
                if not user:
                    return await interaction.followup.send("❌ You need to `/start` first.")

                config = self.bot.config_manager.get_config("data/config/progression_settings") or {}
                player_max_level = config.get("progression", {}).get("player_max_level", 100)

                embed = discord.Embed(
                    title=f"📘 {interaction.user.display_name}'s Profile",
                    description=random.choice(FLAVOR_QUOTES),
                    color=discord.Color.teal()
                )
                embed.add_field(name="Level", value=f"{user.level}/{user.level_cap}", inline=True)
                
                # --- FIX: Call the prog_manager instance correctly ---
                next_xp = self.prog_manager.get_player_xp_for_next_level(user.level)
                embed.add_field(name="XP", value=f"{user.xp:,} / {next_xp:,}", inline=True)

                next_trial = self.prog_manager.get_next_trial_info(user.level)
                if next_trial:
                    embed.add_field(
                        name="Next Trial Unlock",
                        value=f"Level {next_trial['unlocks_at_level']} (Cap {next_trial['raises_cap_to']})",
                        inline=True
                    )

                currency_text = (
                    f"💰 Faylen: `{getattr(user, 'faylen', 0):,}`\n"
                    f"🔷 Virelite: `{getattr(user, 'virelite', 0):,}`\n"
                    f"🪙 Fayrites: `{getattr(user, 'fayrites', 0):,}`"
                )
                embed.add_field(name="Core Currencies", value=currency_text, inline=False)

                # --- FIX: Optimized Team Query (Solves N+1 Problem) ---
                team_ids = [eid for eid in [user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id] if eid]
                team_esprits = {}
                if team_ids:
                    result = await session.execute(
                        select(UserEsprit).where(UserEsprit.id.in_(team_ids)).options(selectinload(UserEsprit.esprit_data))
                    )
                    team_esprits = {str(e.id): e for e in result.scalars().all()}
                
                team_list_str = []
                team_roles = {"active_esprit_id": "👑 Leader", "support1_esprit_id": "⚔️ Support 1", "support2_esprit_id": "🛡️ Support 2"}
                
                for role_attr, role_name in team_roles.items():
                    esprit_id = getattr(user, role_attr)
                    esprit = team_esprits.get(esprit_id)
                    if esprit and esprit.esprit_data:
                        # Display UID and next trial level if relevant
                        uid = str(esprit.id)[:6]
                        team_list_str.append(f"**{role_name}:** {esprit.esprit_data.name} `Lv.{esprit.current_level}` (`{uid}`)")
                    else:
                        team_list_str.append(f"**{role_name}:** _Empty_")

                embed.add_field(name="Active Team", value="\n".join(team_list_str), inline=False)
                embed.set_footer(text=f"Joined on {user.created_at.strftime('%Y-%m-%d')}")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Profile command failed for user {interaction.user.id}")
            await interaction.followup.send("❌ Something went wrong loading your profile.")

    @app_commands.command(name="level", description="Check your current level and XP progression.")
    async def level(self, interaction: discord.Interaction):
        # This command is largely redundant with /profile now, but keeping the logic corrected.
        await interaction.response.defer()
        try:
            if not await self.check_rate_limit(interaction):
                return

            async with get_session() as session:
                user = await session.get(User, str(interaction.user.id))
                if not user:
                    return await interaction.followup.send("❌ You need to `/start` first.")

                if user.level >= user.level_cap:
                    next_xp_disp = "MAX"
                    bar = "█" * 10
                    percent = 1.0
                else:
                    # --- FIX: Call the prog_manager instance correctly ---
                    next_xp = self.prog_manager.get_player_xp_for_next_level(user.level)
                    next_xp_disp = f"{next_xp:,}"
                    percent = user.xp / next_xp if next_xp > 0 else 1.0
                    blocks = int(percent * 10)
                    bar = "█" * blocks + "░" * (10 - blocks)
                
                embed = discord.Embed(
                    title=f"📈 {interaction.user.display_name}'s Level Progression",
                    color=discord.Color.green()
                )
                embed.add_field(name="Level", value=f"{user.level}/{user.level_cap}", inline=True)
                embed.add_field(name="Current XP", value=f"{user.xp:,}", inline=True)
                embed.add_field(name="Next Level XP", value=next_xp_disp, inline=True)
                embed.add_field(name="Progress", value=f"`[{bar}]` {percent:.1%}", inline=False)
                await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Level command failed for user {interaction.user.id}")
            await interaction.followup.send("❌ Failed to load level information.")

    @app_commands.command(name="botinfo", description="View information and statistics about the Faye bot.")
    async def botinfo(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            config = self.bot.config_manager.get_config("data/config/bot_settings") or {}
            bot_info = config.get("bot_info", {})
            
            uptime_str = "Unknown"
            if hasattr(self.bot, 'start_time'):
                 uptime_str = discord.utils.format_dt(self.bot.start_time, "R")

            # --- FIX: Modern, ORM-based queries ---
            async with get_session() as session:
                user_count_res = await session.execute(select(func.count(User.user_id)))
                user_count = user_count_res.scalar_one_or_none() or 0
                
                esprit_count_res = await session.execute(select(func.count(UserEsprit.id)))
                esprit_count = esprit_count_res.scalar_one_or_none() or 0

            embed = discord.Embed(
                title=f"{self.bot.user.name} Information",
                description=bot_info.get("description", "The Next Evolution of Discord Engagement."),
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
            embed.add_field(name="Version", value=bot_info.get("version", "N/A"), inline=True)
            embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}", inline=True)
            embed.add_field(name="Uptime", value=uptime_str, inline=True)
            embed.add_field(name="Total Users", value=f"{user_count:,}", inline=True)
            embed.add_field(name="Total Esprits", value=f"{esprit_count:,}", inline=True)
            embed.add_field(name="Developer", value=bot_info.get("developer_name", "Unknown"), inline=True)
            embed.add_field(name="Website", value=f"[{bot_info.get('website_url', 'faye.bot')}]({bot_info.get('website_url', 'https://faye.bot')})", inline=False)
            embed.set_footer(text="Built with Python, discord.py, and SQLModel.")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Botinfo command failed")
            await interaction.followup.send("❌ Couldn't load bot information.")

async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
    logger.info("✅ UtilityCog loaded")


