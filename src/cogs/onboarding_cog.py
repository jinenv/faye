# src/cogs/onboarding_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import random
from sqlalchemy.future import select

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger

logger = get_logger(__name__)

class OnboardingCog(commands.Cog):
    """Handles the player onboarding process."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load the entire starter currency dictionary
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.STARTER_CURRENCIES = game_settings.get("starter_currencies", {})

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
            
            # Create a new user with currencies from the config
            new_user = User(
                user_id=str(interaction.user.id),
                username=interaction.user.display_name,
                level=1,
                xp=0,
                nyxies=self.STARTER_CURRENCIES.get("nyxies", 0),
                moonglow=self.STARTER_CURRENCIES.get("moonglow", 0),
                azurite_shards=self.STARTER_CURRENCIES.get("azurite_shards", 0),
                essence=self.STARTER_CURRENCIES.get("essence", 0),
                loot_chests=0
            )
            
            session.add(new_user)
            await session.flush()

            new_user_esprit = UserEsprit(owner_id=new_user.user_id, esprit_data_id=chosen_esprit.esprit_id, current_hp=chosen_esprit.base_hp, current_level=1, current_xp=0)
            session.add(new_user_esprit)
            await session.flush()
            
            new_user.active_esprit_id = new_user_esprit.id
            session.add(new_user)
            await session.commit()
            
            logger.info(f"New user registered: {interaction.user.display_name} ({interaction.user.id})")
            
            # Create a more detailed welcome message
            start_nyxies = self.STARTER_CURRENCIES.get("nyxies", 0)
            start_shards = self.STARTER_CURRENCIES.get("azurite_shards", 0)
            
            embed = discord.Embed(
                title="🚀 Adventure Awaits!",
                description=f"Welcome, **{interaction.user.display_name}**! An account has been created for you.",
                color=discord.Color.green()
            )
            embed.add_field(name="🎁 Starting Bonus", value=f"• **{start_nyxies:,}** Nyxies\n• **{start_shards}** Azurite Shards", inline=False)
            embed.add_field(name="🌟 Your First Esprit", value=f"You received an Epic Esprit: **{chosen_esprit.name}**!", inline=False)
            embed.set_footer(text="Use /help to see all available commands.")
            
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(OnboardingCog(bot))
    logger.info("✅ OnboardingCog loaded")
