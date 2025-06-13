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
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.STARTER_CURRENCIES = game_settings.get("starter_currencies", {})
        self.STARTER_RARITY = (game_settings.get("onboarding", {}) or {}).get("starter_esprit_rarity", "Epic")

    @app_commands.command(name="start", description="Begin your adventure and get your starting bonus.")
    async def start(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            existing = await session.get(User, str(interaction.user.id))
            if existing:
                await interaction.followup.send(embed=discord.Embed(
                    title="🔄 Already Registered",
                    description="You already have an account! Use other commands to play.",
                    color=discord.Color.orange()
                ))
                return

            stmt = select(EspritData).where(EspritData.rarity == self.STARTER_RARITY)
            starter_pool = (await session.execute(stmt)).scalars().all()
            if not starter_pool:
                logger.error(f"CRITICAL: No {self.STARTER_RARITY}-tier Esprits found for the start command.")
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ Error",
                    description=f"Could not find any {self.STARTER_RARITY}-tier Esprits to give you. Please contact an admin.",
                    color=discord.Color.red()
                ))
                return

            chosen_esprit = random.choice(starter_pool)
            
            # Create a new user with currencies from the config
            new_user = User(
                user_id=str(interaction.user.id),
                username=interaction.user.display_name,
                level=1,
                xp=0,
                nyxies=self.STARTER_CURRENCIES.get("nyxies", 0),
                moonglow=self.STARTER_CURRENCIES.get("moonglow", 0),
                azurite_shards=self.STARTER_CURRENCIES.get("azurite_shards", 0),
                aether=self.STARTER_CURRENCIES.get("aether", 0),
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
            start_moonglow = self.STARTER_CURRENCIES.get("moonglow", 0)
            start_shards = self.STARTER_CURRENCIES.get("azurite_shards", 0)
            start_aether = self.STARTER_CURRENCIES.get("aether", 0)
            if start_nyxies < 0 or start_shards < 0 or start_aether < 0:
                logger.error("Negative starting currencies detected! Please check your game settings.")
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ Error",
                    description="Invalid starting currencies configuration. Please contact an admin.",
                    color=discord.Color.red()
                ))
                return
            
            embed = discord.Embed(
                title="🚀 Adventure Awaits!",
                description=f"Welcome, **{interaction.user.display_name}**! An account has been created for you.",
                color=discord.Color.green()
            )
            embed.add_field(name="🎁 Starting Bonus", value=f"• **{start_nyxies:,}** Nyxies\n• **{start_moonglow}** Moonglow\n• **{start_shards}** Azurite Shards\n• **{start_aether:,}** Aether", inline=False)
            embed.add_field(name="🌟 Your First Esprit", value=f"You received an Epic Esprit: **{chosen_esprit.name}**!", inline=False)
            embed.set_footer(text="Use /help to see all available commands.")
            
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(OnboardingCog(bot))
    logger.info("✅ OnboardingCog loaded")
