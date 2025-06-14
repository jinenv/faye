# src/cogs/utility_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.db import get_session
from src.database.models import User, UserEsprit
from src.utils.logger import get_logger
# --- 1. IMPORT RATE LIMITER ---
from src.utils.rate_limiter import RateLimiter

logger = get_logger(__name__)

class UtilityCog(commands.Cog, name="Utility"):
    """
    Houses informational and utility-focused commands for players.
    Provides access to profiles, progression details, and bot info.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # --- 2. INITIALIZE RATE LIMITER ---
        self.limiter = RateLimiter(calls=5, period=20) # General purpose limit

    @app_commands.command(name="profile", description="View your complete player profile and active team.")
    async def profile(self, interaction: discord.Interaction):
        """Displays a comprehensive summary of the player's account."""
        await interaction.response.defer(ephemeral=True)

        # --- 3. ADD RATE LIMIT CHECK ---
        if not await self.limiter.check(str(interaction.user.id)):
            wait = await self.limiter.get_cooldown(str(interaction.user.id))
            return await interaction.followup.send(f"You're using commands too quickly! Please wait {wait}s.", ephemeral=True)
        
        async with get_session() as session:
            # ... (rest of the profile logic remains the same)
            # This logic is already solid.
            pass

    @app_commands.command(name="level", description="Check your current level and XP progression.")
    async def level(self, interaction: discord.Interaction):
        """Provides a detailed view of the player's XP and level-up progress."""
        await interaction.response.defer(ephemeral=True)

        # --- 3. ADD RATE LIMIT CHECK ---
        if not await self.limiter.check(str(interaction.user.id)):
            wait = await self.limiter.get_cooldown(str(interaction.user.id))
            return await interaction.followup.send(f"You're using commands too quickly! Please wait {wait}s.", ephemeral=True)
        
        async with get_session() as session:
            # ... (rest of the level logic remains the same)
            # This logic is also solid.
            pass

    @app_commands.command(name="botinfo", description="View information and statistics about the Nyxa bot.")
    async def botinfo(self, interaction: discord.Interaction):
        """Displays general bot statistics, version, and useful links."""
        await interaction.response.defer(ephemeral=True)
        
        # --- 4. LOAD INFO FROM CONFIG ---
        bot_info_config = self.bot.config_manager.get_config("data/config/game_settings").get("bot_info", {})
        version = bot_info_config.get("version", "N/A")
        developer = bot_info_config.get("developer_name", "Unknown")
        website = bot_info_config.get("website_url", "https://nyxa.bot") # Fallback just in case

        embed = discord.Embed(
            title="Nyxa Bot Information",
            description="The Next Evolution of Discord Engagement.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Version", value=version, inline=True)
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds)}", inline=True)
        embed.add_field(name="Uptime", value=discord.utils.format_dt(getattr(self.bot, 'start_time', discord.utils.utcnow()), "R"), inline=True)
        embed.add_field(name="Developer", value=developer, inline=True)
        embed.add_field(name="Website", value=f"[{website.replace('https://', '')}]({website})", inline=False)
        embed.set_footer(text="Built with Python, discord.py, and SQLModel.")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
    logger.info("✅ UtilityCog loaded")