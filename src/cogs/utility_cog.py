# src/cogs/utility_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

from src.database.db import get_session
from src.database.models import User, UserEsprit
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiter
from src.utils import progression_manager

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

    async def check_rate_limit(self, interaction: discord.Interaction) -> bool:
        if not await self.limiter.check(str(interaction.user.id)):
            wait = await self.limiter.get_cooldown(str(interaction.user.id)) or 10
            await interaction.followup.send(
                f"You're using commands too quickly! Please wait {wait}s."
            )
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
                progression_cfg = config.get("progression", {})
                player_max_level = progression_cfg.get("player_max_level", 100)

                embed = discord.Embed(
                    title=f"📘 {interaction.user.display_name}'s Profile",
                    description="Your profile and team summary.",
                    color=discord.Color.teal()
                )
                # Main stats
                embed.add_field(name="Level", value=f"{user.level}/{player_max_level}", inline=True)
                embed.add_field(name="XP", value=str(user.xp), inline=True)

                # Currencies
                embed.add_field(
                    name="Currencies",
                    value=(
                        f"💰 Faylen: `{getattr(user, 'faylen', 0):,}`\n"
                        f"🔷 Virelite: `{getattr(user, 'virelite', 0):,}`\n"
                        f"🪙 Fayrites: `{getattr(user, 'fayrites', 0):,}`\n"
                        f"🪨 Shards: `{getattr(user, 'fayrite_shards', 0):,}`\n"
                        f"🧪 Remna: `{getattr(user, 'remna', 0):,}`\n"
                        f"✨ Ethryl: `{getattr(user, 'ethryl', 0):,}`\n"
                        f"🎁 Loot Chests: `{getattr(user, 'loot_chests', 0):,}`"
                    ),
                    inline=False,
                )

                # Team preview
                team_ids = [user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id]
                esprit_list = []
                esprit_names = ["Active", "Support 1", "Support 2"]
                for idx, eid in enumerate(team_ids):
                    if eid:
                        esprit = await session.get(UserEsprit, eid)
                        if esprit and esprit.esprit_data:
                            esprit_list.append(
                                f"**{esprit_names[idx]}:** {esprit.esprit_data.name} "
                                f"(⭐ {esprit.esprit_data.rarity}) Lv.{esprit.current_level}"
                            )
                        else:
                            esprit_list.append(f"**{esprit_names[idx]}:** _None_")
                    else:
                        esprit_list.append(f"**{esprit_names[idx]}:** _None_")
                embed.add_field(name="Active Team", value="\n".join(esprit_list), inline=False)

                # Last daily claim
                last_claim = getattr(user, "last_daily_claim", None)
                claim_str = discord.utils.format_dt(last_claim, "R") if last_claim else "No claim yet"
                embed.add_field(name="Last Daily Claim", value=claim_str, inline=False)

                # Flavor quote
                embed.set_footer(text=random.choice(FLAVOR_QUOTES))

                await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Profile command failed for user {interaction.user.id}")
            await interaction.followup.send("❌ Something went wrong loading your profile.")

    @app_commands.command(name="level", description="Check your current level and XP progression.")
    async def level(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            if not await self.check_rate_limit(interaction):
                return

            async with get_session() as session:
                user = await session.get(User, str(interaction.user.id))
                if not user:
                    return await interaction.followup.send("❌ You need to `/start` first.")

                config = self.bot.config_manager.get_config("data/config/progression_settings") or {}
                progression_cfg = config.get("progression", {})
                player_max_level = progression_cfg.get("player_max_level", 100)

                next_xp = progression_manager.get_player_xp_for_next_level(user.level, progression_cfg)
                if user.level >= player_max_level or next_xp == 0:
                    next_xp_disp = "MAX"
                    bar = "█" * 10
                    percent = 1.0
                else:
                    next_xp_disp = f"{next_xp:,}"
                    percent = user.xp / next_xp if next_xp else 1.0
                    blocks = int(percent * 10)
                    bar = "█" * blocks + "░" * (10 - blocks)

                embed = discord.Embed(
                    title=f"📈 {interaction.user.display_name}'s Level Progression",
                    color=discord.Color.green()
                )
                embed.add_field(name="Level", value=f"{user.level}/{player_max_level}", inline=True)
                embed.add_field(name="Current XP", value=str(user.xp), inline=True)
                embed.add_field(name="Next Level XP", value=next_xp_disp, inline=True)
                embed.add_field(name="Progress", value=f"`[{bar}]` {percent:.0%}", inline=False)
                embed.set_footer(text="Progression info from config.")
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
            version = bot_info.get("version", "N/A")
            developer = bot_info.get("developer_name", "Unknown")
            website = bot_info.get("website_url", "https://faye.bot")
            uptime = getattr(self.bot, 'start_time', None)
            if uptime:
                uptime_str = discord.utils.format_dt(uptime, "R")
            else:
                uptime_str = "Unknown"

            # Global stats
            guilds = getattr(self.bot, 'guilds', [])
            async with get_session() as session:
                user_count = await session.exec("SELECT COUNT(*) FROM users")
                user_count = user_count.one() if hasattr(user_count, "one") else "?"
                esprit_count = await session.exec("SELECT COUNT(*) FROM user_esprits")
                esprit_count = esprit_count.one() if hasattr(esprit_count, "one") else "?"

            embed = discord.Embed(
                title="Faye Bot Information",
                description="The Next Evolution of Discord Engagement.",
                color=discord.Color.gold()
            )
            embed.add_field(name="Version", value=version, inline=True)
            embed.add_field(name="Servers", value=f"{len(guilds)}", inline=True)
            embed.add_field(name="Uptime", value=uptime_str, inline=True)
            embed.add_field(name="Users", value=f"{user_count}", inline=True)
            embed.add_field(name="Esprits", value=f"{esprit_count}", inline=True)
            embed.add_field(name="Developer", value=developer, inline=True)
            embed.add_field(name="Website", value=f"[{website.replace('https://', '')}]({website})", inline=False)
            embed.set_footer(text="Built with Python, discord.py, and SQLModel.")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Botinfo command failed for user {interaction.user.id}")
            await interaction.followup.send("❌ Couldn't load bot information.")

async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
    logger.info("✅ UtilityCog loaded")


