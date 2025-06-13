# src/cogs/utility_cog.py

import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.db import get_session
from src.database.models import User, UserEsprit
from src.utils.logger import get_logger
from src.utils.progression_manager import ProgressionManager

logger = get_logger(__name__)

class UtilityCog(commands.Cog, name="Utility"):
    """
    Houses informational and utility-focused commands for players.
    Provides access to profiles, progression details, and bot info.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize the progression manager to calculate XP requirements
        self.progression_manager = ProgressionManager(self.bot.config_manager)

    @app_commands.command(name="profile", description="View your complete player profile and active team.")
    async def profile(self, interaction: discord.Interaction):
        """Displays a comprehensive summary of the player's account."""
        await interaction.response.defer(ephemeral=True)
        
        async with get_session() as session:
            # Fetch the user from the database
            user = await session.get(User, str(interaction.user.id))

            if not user:
                await interaction.followup.send("❌ You haven't started your adventure yet. Use `/start` to begin.", ephemeral=True)
                return

            # Fetch active esprit data if it exists
            active_esprit_text = "None. Use `/esprit equip`."
            if user.active_esprit_id:
                stmt = select(UserEsprit).where(UserEsprit.id == user.active_esprit_id).options(selectinload(UserEsprit.esprit_data))
                active_esprit = (await session.execute(stmt)).scalar_one_or_none()
                if active_esprit and active_esprit.esprit_data:
                    ed = active_esprit.esprit_data
                    ue = active_esprit
                    active_esprit_text = f"**{ed.name}**\nLvl. {ue.current_level} | {ed.rarity} {ed.class_name}"

            # Create the embed
            embed = discord.Embed(
                title=f"{interaction.user.display_name}'s Profile",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

            # --- Player Progression ---
            xp_needed = self.progression_manager.get_player_xp_for_next_level(user.level)
            progress_percent = (user.xp / xp_needed * 100) if xp_needed > 0 else 100
            
            filled_blocks = int(progress_percent / 10)
            empty_blocks = 10 - filled_blocks
            progress_bar = f"[`{'█' * filled_blocks}{'░' * empty_blocks}`]"

            embed.add_field(
                name="Player Level",
                value=f"**Level {user.level}**\n{user.xp:,} / {xp_needed:,} XP\n{progress_bar} {progress_percent:.1f}%",
                inline=False
            )

            # --- Active Esprit ---
            embed.add_field(name="Active Esprit", value=active_esprit_text, inline=True)

            # --- Currencies ---
            azurites = user.azurite_shards // 10
            shards = user.azurite_shards % 10
            currency_text = (
                f"**Nyxies:** {user.nyxies:,}\n"
                f"**Moonglow:** {user.moonglow:,}\n"
                f"**Azurites:** {azurites:,} ({shards}/10 shards)\n"
                f"**Aether:** {user.aether:,}\n"
                f"**Essence:** {user.essence:,}\n"
                f"**Loot Chests:** {user.loot_chests:,}"
            )
            embed.add_field(name="Wallet", value=currency_text, inline=True)

            embed.set_footer(text=f"Joined: {discord.utils.format_dt(user.created_at, style='D')}")

            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="level", description="Check your current level and XP progression.")
    async def level(self, interaction: discord.Interaction):
        """Provides a detailed view of the player's XP and level-up progress."""
        await interaction.response.defer(ephemeral=True)
        # TODO: Logic to fetch user's XP, current level, and XP needed for next level.
        await interaction.followup.send("🚧 This command is under construction. It will soon show your XP details!")

    @app_commands.command(name="botinfo", description="View information and statistics about the Nyxa bot.")
    async def botinfo(self, interaction: discord.Interaction):
        """Displays general bot statistics, version, and useful links."""
        await interaction.response.defer(ephemeral=True)
        # TODO: Logic to display bot uptime, server count, player count, and links.
        embed = discord.Embed(
            title="Nyxa Bot Information",
            description="The Next Evolution of Discord Engagement.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Version", value="0.4.0 (Alembic Integration)", inline=True)
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds)}", inline=True)
        embed.add_field(name="Developer", value="Your Developer Name", inline=True)
        embed.add_field(name="Website", value="[nyxa.bot](https://nyxa.bot)", inline=False)
        embed.set_footer(text="Built with Python, discord.py, and SQLModel.")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
    logger.info("✅ UtilityCog loaded")