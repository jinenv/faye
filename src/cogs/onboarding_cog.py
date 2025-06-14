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
        
        # Get onboarding settings with better error handling
        onboarding_settings = game_settings.get("onboarding", {})
        self.STARTER_RARITY = onboarding_settings.get("starter_esprit_rarity", "Epic")
        self.STARTER_LEVEL = onboarding_settings.get("starter_esprit_level", 1)
        
        # Validate configuration on startup
        if not self.STARTER_CURRENCIES:
            logger.warning("No starter currencies configured - users will start with 0 of everything!")
            
        valid_rarities = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"]
        if self.STARTER_RARITY not in valid_rarities:
            logger.error(f"Invalid starter rarity '{self.STARTER_RARITY}' - must be one of: {valid_rarities}")
            self.STARTER_RARITY = "Epic"  # Fallback to safe default
            
        if not isinstance(self.STARTER_LEVEL, int) or self.STARTER_LEVEL < 1:
            logger.error(f"Invalid starter level '{self.STARTER_LEVEL}' - must be positive integer")
            self.STARTER_LEVEL = 1  # Fallback to safe default
            
        logger.info(f"Onboarding configured: {self.STARTER_RARITY} rarity, level {self.STARTER_LEVEL}")

    @app_commands.command(name="start", description="Begin your adventure and get your starting bonus.")
    async def start(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            async with get_session() as session:
                # Check if user already exists
                existing = await session.get(User, str(interaction.user.id))
                if existing:
                    await interaction.followup.send(embed=discord.Embed(
                        title="🔄 Already Registered",
                        description="You already have an account! Use other commands to play.",
                        color=discord.Color.orange()
                    ))
                    return

                # Get starter Esprit pool
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

                chosen_esprit = random.choice(starter_pool)
                
                # Validate starting currencies
                start_nyxies = self.STARTER_CURRENCIES.get("nyxies", 0)
                start_moonglow = self.STARTER_CURRENCIES.get("moonglow", 0)
                start_shards = self.STARTER_CURRENCIES.get("azurite_shards", 0)
                start_aether = self.STARTER_CURRENCIES.get("aether", 0)
                start_essence = self.STARTER_CURRENCIES.get("essence", 0)
                
                if any(val < 0 for val in [start_nyxies, start_moonglow, start_shards, start_aether, start_essence]):
                    logger.error("CRITICAL: Negative starting currencies detected in configuration!")
                    await interaction.followup.send(embed=discord.Embed(
                        title="❌ Configuration Error",
                        description="Invalid starting currencies configuration. Please contact an administrator.",
                        color=discord.Color.red()
                    ))
                    return
                
                # Create new user
                new_user = User(
                    user_id=str(interaction.user.id),
                    username=interaction.user.display_name,
                    level=1,
                    xp=0,
                    nyxies=start_nyxies,
                    moonglow=start_moonglow,
                    azurite_shards=start_shards,
                    aether=start_aether,
                    essence=start_essence,
                    loot_chests=0
                )
                
                session.add(new_user)
                await session.flush()

                # Create starter Esprit
                new_user_esprit = UserEsprit(
                    owner_id=new_user.user_id, 
                    esprit_data_id=chosen_esprit.esprit_id, 
                    current_hp=chosen_esprit.base_hp, 
                    current_level=self.STARTER_LEVEL,  # Use configured starter level
                    current_xp=0
                )
                session.add(new_user_esprit)
                await session.flush()
                
                # Set active Esprit
                new_user.active_esprit_id = new_user_esprit.id
                session.add(new_user)
                await session.commit()
                
                logger.info(f"New user registered: {interaction.user.display_name} ({interaction.user.id}) with starter Esprit: {chosen_esprit.name}")
                
                # Create welcome embed
                embed = discord.Embed(
                    title="🚀 Adventure Awaits!",
                    description=f"Welcome, **{interaction.user.display_name}**! Your account has been created and your journey begins now.",
                    color=discord.Color.green()
                )
                
                # Build currency display dynamically
                currency_lines = []
                if start_nyxies > 0:
                    currency_lines.append(f"• **{start_nyxies:,}** Nyxies")
                if start_moonglow > 0:
                    currency_lines.append(f"• **{start_moonglow:,}** Moonglow")
                if start_shards > 0:
                    currency_lines.append(f"• **{start_shards:,}** Azurite Shards")
                if start_aether > 0:
                    currency_lines.append(f"• **{start_aether:,}** Aether")
                if start_essence > 0:
                    currency_lines.append(f"• **{start_essence:,}** Essence")
                
                if currency_lines:
                    embed.add_field(
                        name="🎁 Starting Resources", 
                        value="\n".join(currency_lines), 
                        inline=False
                    )
                
                embed.add_field(
                    name="🌟 Your First Esprit", 
                    value=f"You received a **{chosen_esprit.rarity}** Esprit: **{chosen_esprit.name}**",
                    inline=False
                )
                embed.set_footer(text="Use /help to see all available commands and start your adventure!")
                
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in start command for user {interaction.user.id}: {str(e)}")
            await interaction.followup.send(embed=discord.Embed(
                title="❌ Unexpected Error",
                description="Something went wrong during registration. Please try again or contact an administrator.",
                color=discord.Color.red()
            ))

async def setup(bot: commands.Bot):
    await bot.add_cog(OnboardingCog(bot))
    logger.info("✅ OnboardingCog loaded")