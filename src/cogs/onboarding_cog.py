# src/cogs/onboarding_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import random
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger

logger = get_logger(__name__)

class OnboardingCog(commands.Cog):
    """Handles the player onboarding process."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.START_GOLD = game_settings.get("starting_gold", 1000)

    @app_commands.command(name="start", description="Begin your adventure and get your starting bonus.")
    async def start(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            existing = await session.get(User, str(interaction.user.id))
            if existing:
                await interaction.followup.send(embed=discord.Embed(title="🔄 Already Registered", description="You already have an account! Use other commands to play.", color=discord.Color.orange()))
                return

            stmt = select(EspritData).where(EspritData.rarity == "Epic")
            epic_pool = (await session.execute(stmt)).scalars().all()
            if not epic_pool:
                logger.error("CRITICAL: No Epic-tier Esprits found for the start command.")
                await interaction.followup.send(embed=discord.Embed(title="❌ Error", description="Could not find any Epic-tier Esprits to give you. Please contact an admin.", color=discord.Color.red()))
                return

            chosen_esprit = random.choice(epic_pool)
            new_user = User(user_id=str(interaction.user.id), username=interaction.user.display_name, level=1, xp=0, gold=self.START_GOLD, dust=0, fragments=0, loot_chests=0)
            
            session.add(new_user)
            await session.flush()

            new_user_esprit = UserEsprit(owner_id=new_user.user_id, esprit_data_id=chosen_esprit.esprit_id, current_hp=chosen_esprit.base_hp, current_level=1, current_xp=0)
            session.add(new_user_esprit)
            await session.flush()
            
            new_user.active_esprit_id = new_user_esprit.id
            session.add(new_user)
            await session.commit()
            
            logger.info(f"New user registered: {interaction.user.display_name} ({interaction.user.id})")
            embed = discord.Embed(title="🚀 Adventure Awaits!", description=f"Welcome, **{interaction.user.display_name}**!\nAn account has been created for you. You received **{self.START_GOLD} gold** and an Epic Esprit: **{chosen_esprit.name}**.", color=discord.Color.green())
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(OnboardingCog(bot))
