# src/cogs/summon_cog.py

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
        self.rng = RNGManager()

        # Load rarity tiers
        self.rarity_tiers = self.config_manager.get_config('data/config/rarity_tiers')
        if not self.rarity_tiers or not isinstance(self.rarity_tiers, dict) or 'rarity_weights' not in self.rarity_tiers:
            logger.error("SummonCog: Invalid or missing rarity_tiers config.")
            self.rarity_weights = {}
        else:
            self.rarity_weights = self.rarity_tiers["rarity_weights"]
            logger.info(f"Loaded {len(self.rarity_weights)} rarity tiers")

        # Load esprits
        self.esprits_data = self.config_manager.get_config('data/config/esprits')
        if not self.esprits_data or not isinstance(self.esprits_data, dict) or "esprits" not in self.esprits_data:
            logger.error("SummonCog: Invalid or missing esprits config.")
            self.esprits = []
        else:
            self.esprits = self.esprits_data["esprits"]
            logger.info(f"Loaded {len(self.esprits)} Esprits")

    @app_commands.command(name="summon", description="Summon a random Esprit from the ethereal void.")
    async def summon(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        try:
            if not self.rarity_weights or not self.esprits:
                logger.error(f"Summon command by {interaction.user.name} failed due to missing config.")
                await interaction.followup.send(
                    "Summoning config is missing required data. Contact the dev.",
                    ephemeral=True
                )
                return

            rarity = self.rng.get_random_rarity(
                {"rarity_weights": self.rarity_weights},
                luck_modifier=0
            )

            if not rarity:
                await interaction.followup.send("Could not determine rarity. Try again.", ephemeral=True)
                return

            filtered = [e for e in self.esprits if e.get("rarity") == rarity]
            if not filtered:
                await interaction.followup.send(f"No Esprits available for rarity: {rarity}", ephemeral=True)
                return

            chosen = random.choice(filtered)
            logger.info(f"{interaction.user.name} summoned: {chosen.get('name')} ({rarity})")

            embed = discord.Embed(
                title="✨ Summoning Result ✨",
                description=f"{interaction.user.mention}, you have summoned:",
                color=discord.Color.random()
            )
            embed.add_field(name=f"**{chosen.get('name')}**", value=f"Rarity: *{rarity}*", inline=False)
            embed.add_field(name="Description", value=chosen.get("description", "???"), inline=False)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Unhandled error in /summon: {e}", exc_info=True)
            await interaction.followup.send("An unexpected error occurred. Try again later.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))
