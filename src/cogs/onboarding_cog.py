# src/cogs/onboarding_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import random
from sqlalchemy.future import select

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger
# --- 1. IMPORT THE TRANSACTION LOGGER ---
from src.utils import transaction_logger

logger = get_logger(__name__)

class OnboardingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        self.STARTER_CURRENCIES = game_settings.get("starter_currencies", {})
        
        onboarding_settings = game_settings.get("onboarding", {})
        self.STARTER_RARITY = onboarding_settings.get("starter_esprit_rarity", "Epic")
        self.STARTER_LEVEL = onboarding_settings.get("starter_esprit_level", 1)
        
        # This validation remains excellent. No changes needed here.
        if not self.STARTER_CURRENCIES:
            logger.warning("No starter currencies configured - users will start with 0 of everything!")
            
        valid_rarities = ["Common", "Uncommon", "Rare", "Epic", "Celestial", "Supreme", "Deity", "Legendary", "Mythic"]
        if self.STARTER_RARITY not in valid_rarities:
            logger.error(f"Invalid starter rarity '{self.STARTER_RARITY}' - must be one of: {valid_rarities}")
            self.STARTER_RARITY = "Epic"
            
        if not isinstance(self.STARTER_LEVEL, int) or self.STARTER_LEVEL < 1:
            logger.error(f"Invalid starter level '{self.STARTER_LEVEL}' - must be a positive integer")
            self.STARTER_LEVEL = 1
            
        logger.info(f"Onboarding configured: {self.STARTER_RARITY} rarity, level {self.STARTER_LEVEL}")

    @app_commands.command(name="start", description="Begin your adventure and get your starting bonus.")
    async def start(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
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
                        title="❌ Configuration Error",
                        description=f"No {self.STARTER_RARITY}-tier Esprits available. Please contact an administrator.",
                        color=discord.Color.red()
                    ))
                    return

                chosen_esprit_data = random.choice(starter_pool)
                
                # Create new user, directly using the STARTER_CURRENCIES dictionary
                new_user = User(
                    user_id=str(interaction.user.id),
                    username=interaction.user.display_name,
                    level=1,
                    xp=0,
                    **self.STARTER_CURRENCIES
                )
                
                session.add(new_user)
                await session.flush()

                # Create starter Esprit
                new_user_esprit = UserEsprit(
                    owner_id=new_user.user_id, 
                    esprit_data_id=chosen_esprit_data.esprit_id, 
                    current_hp=chosen_esprit_data.base_hp, 
                    current_level=self.STARTER_LEVEL,
                )
                session.add(new_user_esprit)
                await session.flush()
                
                new_user.active_esprit_id = new_user_esprit.id
                session.add(new_user)
                
                await session.commit()
                
                # --- 2. CALL THE DEDICATED TRANSACTION LOGGER ---
                transaction_logger.log_new_user_registration(
                    interaction, new_user, chosen_esprit_data, self.STARTER_CURRENCIES
                )
                
                # --- 3. IMPROVED DYNAMIC CURRENCY DISPLAY ---
                embed = discord.Embed(
                    title="🚀 Adventure Awaits!",
                    description=f"Welcome, **{interaction.user.display_name}**! Your account has been created and your journey begins now.",
                    color=discord.Color.green()
                )
                
                # This now iterates directly over the config dictionary. No more `if` statements needed.
                currency_lines = [f"• **{v:,}** {k.replace('_', ' ').title()}" for k, v in self.STARTER_CURRENCIES.items() if v > 0]
                if currency_lines:
                    embed.add_field(name="🎁 Starting Resources", value="\n".join(currency_lines), inline=False)
                
                embed.add_field(
                    name="🌟 Your First Esprit", 
                    value=f"You received a **{chosen_esprit_data.rarity}** Esprit: **{chosen_esprit_data.name}**",
                    inline=False
                )
                embed.set_footer(text="Use /help to see all available commands and start your adventure!")
                
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in start command for user {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send(embed=discord.Embed(
                title="❌ Unexpected Error",
                description="Something went wrong during registration. Please try again or contact an administrator.",
                color=discord.Color.red()
            ))

async def setup(bot: commands.Bot):
    await bot.add_cog(OnboardingCog(bot))
    logger.info("✅ OnboardingCog loaded")