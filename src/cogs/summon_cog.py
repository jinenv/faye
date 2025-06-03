import discord
from discord.ext import commands
from discord import app_commands
import random

from ..utils.logger import get_logger
from ..utils.config_manager import ConfigManager
from ..utils.rng_manager import RNGManager

logger = get_logger(__name__)

class SummonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = ConfigManager()
        self.rng_manager = RNGManager()

        rarity_path_to_load = 'data/config/rarity_tiers'
        esprit_path_to_load = 'data/config/esprits'
        
        logger.info(f"SummonCog: Attempting to load rarity_tiers from: '{rarity_path_to_load}'")
        self.rarity_tiers = self.config_manager.get_config(rarity_path_to_load)
        # --- ADDED DETAILED LOGGING OF RECEIVED VALUE ---
        logger.info(f"SummonCog: self.rarity_tiers RECEIVED: {type(self.rarity_tiers)} -- Value: {str(self.rarity_tiers)[:200]}") # Log type and first 200 chars of value

        logger.info(f"SummonCog: Attempting to load esprits from: '{esprit_path_to_load}'")
        self.esprits_data = self.config_manager.get_config(esprit_path_to_load)
        # --- ADDED DETAILED LOGGING OF RECEIVED VALUE ---
        logger.info(f"SummonCog: self.esprits_data RECEIVED: {type(self.esprits_data)} -- Value: {str(self.esprits_data)[:200]}") # Log type and first 200 chars of value

        # Check if rarity_tiers is truly populated
        if not self.rarity_tiers or not isinstance(self.rarity_tiers, dict) or not self.rarity_tiers.get('rarity_weights'):
            logger.error("SummonCog: self.rarity_tiers is NOT correctly populated or is missing 'rarity_weights'.")
            self.rarity_tiers = {} # Fallback
        else:
            logger.info("SummonCog: self.rarity_tiers appears to be a populated dictionary with 'rarity_weights'.")

        # Check if esprits_data is truly populated
        if not self.esprits_data or not isinstance(self.esprits_data, dict) or not self.esprits_data.get("esprits") or not isinstance(self.esprits_data.get("esprits"), list):
            logger.error("SummonCog: self.esprits_data is NOT correctly populated, missing 'esprits' key, or 'esprits' is not a list.")
            self.esprits_data = {"esprits": []} # Fallback
        elif not self.esprits_data.get("esprits"): # Specifically check if the esprits list is empty
             logger.warning("SummonCog: self.esprits_data has an 'esprits' key, but the list is EMPTY.")
             # self.esprits_data will retain the empty list in this case.
        else:
            logger.info("SummonCog: self.esprits_data appears to be a populated dictionary with a non-empty 'esprits' list.")
            
    @app_commands.command(name="summon", description="Summon a random Esprit from the ethereal void.")
    async def summon(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        try:
            # More specific checks based on the expected structure
            if not self.rarity_tiers.get('rarity_weights') or not self.esprits_data.get("esprits"):
                logger.error(f"Summon command by {interaction.user.name} failed due to missing or invalid config during execution (checked rarity_weights and esprits list).")
                await interaction.followup.send(
                    "Summoning configuration is missing critical data (rarity weights or Esprits list). "
                    "Please contact the admin.",
                    ephemeral=True
                )
                return

            chosen_rarity_name = self.rng_manager.get_random_rarity(self.rarity_tiers, luck_modifier=0)

            if not chosen_rarity_name:
                await interaction.followup.send("Failed to determine rarity for the summon. Please try again.", ephemeral=True)
                logger.error("RNGManager.get_random_rarity returned None.")
                return

            available_esprits_for_rarity = [
                esprit for esprit in self.esprits_data["esprits"] if esprit.get("rarity") == chosen_rarity_name
            ]

            if not available_esprits_for_rarity:
                await interaction.followup.send(
                    f"No Esprits found for the determined rarity: {chosen_rarity_name}. This might be a configuration issue.",
                    ephemeral=True
                )
                logger.warning(f"No esprits found for rarity: {chosen_rarity_name}. Available esprits in config: {len(self.esprits_data.get('esprits', []))}")
                return

            summoned_esprit_data = random.choice(available_esprits_for_rarity)
            esprit_name = summoned_esprit_data.get("name", "Unknown Esprit")
            esprit_rarity = summoned_esprit_data.get("rarity", "Unknown Rarity")
            esprit_description = summoned_esprit_data.get("description", "No description available.")
            
            logger.info(f"Player {interaction.user.name} (ID: {interaction.user.id}) summoned {esprit_name} (Rarity: {esprit_rarity})")

            embed = discord.Embed(
                title="✨ Summoning Result ✨",
                description=f"Congratulations, {interaction.user.mention}! You have summoned:",
                color=discord.Color.random() 
            )
            embed.add_field(name=f"**{esprit_name}**", value=f"Rarity: *{esprit_rarity}*", inline=False)
            embed.add_field(name="Description", value=esprit_description, inline=False)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in /summon command for {interaction.user.name}: {e}", exc_info=True)
            if interaction.response.is_done(): # Check if already responded or deferred
                await interaction.followup.send("An unexpected error occurred while trying to summon. Please try again later.", ephemeral=True)
            else: # Should not happen if we always defer
                 await interaction.response.send_message("An unexpected error occurred. Please try again later.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))