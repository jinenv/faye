# src/cogs/onboarding_cog.py

import logging
import random
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, insert, update, func
from sqlalchemy.orm import selectinload

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
# +++ Import ConfigManager
from src.utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class OnboardingCog(commands.Cog):
    """
    /start → register a new user, giving them gold and a random Epic Esprit
    based on settings in game_settings.json.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # --- self.START_GOLD = 1000
        # +++ Load game settings from the JSON file.
        cfg = ConfigManager()
        self.game_settings = cfg.get_config("data/config/game_settings") or {}
        self.START_GOLD = self.game_settings.get("starting_gold", 1000)

    @app_commands.command(
        name="start",
        description="Register your account and get your starting bonus."
    )
    async def start(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)

        try:
            async with get_session() as session:
                # 1) Check if the user already exists
                stmt_user = select(User).options(selectinload(User.owned_esprits)).where(User.user_id == user_id)
                res_user = await session.execute(stmt_user)
                existing = res_user.scalar_one_or_none()

                if existing:
                    await interaction.followup.send(
                        f"🔄 You already have an account, **{interaction.user.display_name}**! "
                        f"You have **{existing.gold} gold** and **{len(existing.owned_esprits)} Esprits**.\n"
                        "Use `/balance`, `/inventory`, or `/summon`.",
                        ephemeral=True
                    )
                    return

                # 2) Pick one random Epic‐tier Esprit from EspritData
                stmt_all = select(EspritData).where(EspritData.rarity == "Epic")
                res_all = await session.execute(stmt_all)
                epic_pool = res_all.scalars().all()

                if not epic_pool:
                    await interaction.followup.send(
                        "❌ Could not find any Epic‐tier Esprits to give you. Contact an admin.",
                        ephemeral=True
                    )
                    return

                chosen = random.choice(epic_pool)

                # 3) Insert new User row (created_at will default to the current timestamp)
                new_user = User(
                    user_id=user_id,
                    username=interaction.user.name,
                    level=1,
                    xp=0,
                    gold=self.START_GOLD,
                    dust=0,
                    last_daily_claim=None,
                    active_esprit_id=None
                )
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)

                # 4) Create a UserEsprit for that random Epic
                new_ue = UserEsprit(
                    owner_id=user_id,
                    esprit_data_id=chosen.esprit_id,
                    current_hp=chosen.base_hp,
                    current_level=1,
                    current_xp=0,
                )
                session.add(new_ue)
                await session.commit()
                await session.refresh(new_ue)

                # 5) Set that new Esprit as active_esprit_id
                stmt_set_active = (
                    update(User)
                    .where(User.user_id == user_id)
                    .values(active_esprit_id=new_ue.id)
                )
                await session.execute(stmt_set_active)
                await session.commit()

                # 6) Send a confirmation embed
                embed = discord.Embed(
                    title="🚀 Account Created",
                    description=(
                        f"Welcome, **{interaction.user.display_name}**!\n"
                        f"You received **{self.START_GOLD} gold** and an **Epic Esprit: {chosen.name}**."
                    ),
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as exc:
            logger.critical(f"OnboardingCog: Critical error in /start: {exc}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "A critical error occurred. Please try again later.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "A critical error occurred. Please try again later.", ephemeral=True
                )

    @start.error
    async def start_error(self, interaction: discord.Interaction, error):
        logger.error(f"Error in /start: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Unexpected error. Please try again later.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Unexpected error. Please try again later.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(OnboardingCog(bot))


