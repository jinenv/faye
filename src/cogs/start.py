# src/cogs/start.py
from __future__ import annotations
import random

import discord
from discord.ext import commands
from discord import app_commands
import sqlalchemy as sa
from sqlalchemy.future import select
import uuid

from src.database.db import get_session
from src.database.models import User, EspritData, UserEsprit
from src.utils.config_manager import ConfigManager
from src.utils.image_generator import ImageGenerator
from src.utils.render_helpers import render_pil_to_discord_file
from src.utils.logger import get_logger
from src.views.summon_result import SummonResultView

logger = get_logger(__name__)

class Start(commands.Cog):
    def __init__(self, bot: NyxaBot):
        self.bot = bot
        self.config_manager = ConfigManager()
        self.image_generator = ImageGenerator()
        self.game_settings = self.config_manager.get_config('game_settings')
        self.esprits_data = self.config_manager.get_config('esprits')

        # self.starter_esprit_id = None # <-- REMOVED: Starter is now picked per command execution

    # async def cog_load(self): # <-- REMOVED: Logic moved to the /start command
    #     logger.info("Start cog loaded. Pre-loading starter Esprit data...")
    #     # ... (rest of old cog_load logic) ...

    @app_commands.command(name="start", description="Begin your adventure and summon your first Esprit!")
    async def start(self, interaction: discord.Interaction):
        logger.info(f"[/start] Command received by {interaction.user.display_name} ({interaction.user.id}).")
        await interaction.response.defer(thinking=True)
        logger.info(f"[/start] Response deferred for {interaction.user.display_name}.")

        try:
            async with get_session() as session:
                logger.info(f"[/start] Database session obtained for {interaction.user.display_name}.")

                # 1. Check if user already exists
                user_query = select(User).where(User.user_id == str(interaction.user.id))
                user = await session.execute(user_query)
                user = user.scalar_one_or_none()
                logger.info(f"[/start] User query executed. User exists: {user is not None}.")

                if user:
                    await interaction.followup.send(
                        f"Welcome back, **{interaction.user.display_name}**! "
                        "You've already started your adventure. "
                        "Use `/profile` to view your stats or `/explore` to continue your journey!"
                    )
                    logger.info(f"[/start] Existing user message sent for {interaction.user.display_name}.")
                    return

                # --- NEW: Pick a random starter Esprit *now* ---
                starter_rarity_priority = ['Epic', 'Rare', 'Uncommon', 'Common'] # Or higher if you change your mind!
                chosen_starter_esprit_id = None

                # Fetch all Esprits from DB first to get their actual rarity data
                all_esprit_data_from_db = await session.execute(select(EspritData))
                all_esprit_data_map = {e.esprit_id: e for e in all_esprit_data_from_db.scalars().all()}


                for rarity_tier in starter_rarity_priority:
                    eligible_esprits_for_tier = []
                    # Filter from all loaded EspritData, not just self.esprits_data (which is from JSON cache)
                    for esprit_id, esprit_data_obj in all_esprit_data_map.items():
                        if esprit_data_obj.rarity == rarity_tier: # Access rarity attribute of EspritData object
                            eligible_esprits_for_tier.append((esprit_id, esprit_data_obj))

                    if eligible_esprits_for_tier:
                        chosen_esprit_item = random.choice(eligible_esprits_for_tier)
                        chosen_starter_esprit_id = chosen_esprit_item[0]
                        logger.info(f"[/start] Randomly selected starter Esprit ID: {chosen_starter_esprit_id} (Rarity: {rarity_tier}).")
                        break # Found a starter, stop checking lower rarities

                if not chosen_starter_esprit_id:
                    await interaction.followup.send(
                        "Error: Could not determine a starter Esprit. No eligible Esprits found in database. Please contact an admin."
                    )
                    logger.error("Attempted to start user without any eligible starter Esprits in DB.")
                    return

                # Now fetch the actual EspritData object for the chosen ID
                starter_esprit_data_query = select(EspritData).where(EspritData.esprit_id == chosen_starter_esprit_id)
                starter_esprit_data = await session.execute(starter_esprit_data_query)
                starter_esprit_data = starter_esprit_data.scalar_one_or_none()
                logger.info(f"[/start] Starter Esprit data queried. Found: {starter_esprit_data.name if starter_esprit_data else 'None'}.")

                if not starter_esprit_data: # Should not happen if chosen_starter_esprit_id was set
                    await interaction.followup.send(
                        f"Error: Chosen starter Esprit ID '{chosen_starter_esprit_id}' not found in database. Please contact an admin."
                    )
                    logger.error(f"Chosen starter Esprit ID {chosen_starter_esprit_id} from config not found in DB post-selection.")
                    return
                # --- END NEW LOGIC ---

                # 2. Create a new user profile
                new_user = User(
                    user_id=str(interaction.user.id),
                    username=interaction.user.name,
                    level=self.game_settings['starting_level'],
                    xp=0,
                    gold=self.game_settings['starting_gold'],
                    active_esprit_id=None
                )
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)
                logger.info(f"[/start] New user created and committed: {new_user.username} ({new_user.user_id}).")


                # 4. Create the UserEsprit instance
                new_user_esprit = UserEsprit(
                    owner_id=new_user.user_id,
                    esprit_data_id=starter_esprit_data.esprit_id,
                    current_hp=starter_esprit_data.base_hp,
                    current_level=1,
                    current_xp=0
                )
                session.add(new_user_esprit)
                await session.commit()
                await session.refresh(new_user_esprit)
                logger.info(f"[/start] New UserEsprit created and committed: {new_user_esprit.id} ({starter_esprit_data.name}).")

                # Update the user's active_esprit_id
                new_user.active_esprit_id = new_user_esprit.id
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)
                logger.info(f"[/start] User's active_esprit_id updated for {new_user.username}.")

                # 5. Display a welcome message and the summoned Esprit
                summon_image_file = None
                try:
                    logger.info(f"[/start] Attempting to generate summon image for {starter_esprit_data.name}.")
                    summon_image_pil = await self.image_generator.render_esprit_detail_image(
                        esprit_data_dict=starter_esprit_data.to_dict(),
                        esprit_instance=new_user_esprit
                    )
                    summon_image_file = render_pil_to_discord_file(summon_image_pil, "summon_result.png")
                    logger.info(f"[/start] Summon image generated successfully.")
                except Exception as e:
                    logger.error(f"[/start] Error generating summon image for /start: {e}", exc_info=True)
                    summon_image_file = None

                welcome_message = (
                    f"🎉 Welcome, **{interaction.user.display_name}**! Your adventure in Nyxa begins now!\n\n"
                    f"You've summoned your very first Esprit: **{starter_esprit_data.name}**!\n"
                    f"This brave companion will aid you in your journey. "
                    f"They are a **{starter_esprit_data.rarity}**-tier Esprit."
                )
                logger.info(f"[/start] Sending initial followup message.")
                if summon_image_file:
                    await interaction.followup.send(
                        content=welcome_message,
                        file=summon_image_file
                    )
                else:
                    await interaction.followup.send(content=welcome_message)
                logger.info(f"[/start] Initial followup message sent.")

                # 6. Suggest next steps
                logger.info(f"[/start] Sending next steps message.")
                await interaction.channel.send(
                    f"**What's next, {interaction.user.display_name}?**\n\n"
                    "• Use `/explore` to send your Esprit on an adventure and earn rewards!\n"
                    "• Use `/profile` to check your stats and your Esprits.\n"
                    "• Once you have enough gold, try `/summon` to get more powerful Esprits!"
                )
                logger.info(f"[/start] Next steps message sent. Command finished successfully.")

        except Exception as e:
            logger.critical(f"[/start] Unhandled CRITICAL error in /start command for {interaction.user.display_name}: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.followup.send("An unexpected critical error occurred while starting your adventure. Please try again later or contact support.", ephemeral=True)
                else:
                    logger.info(f"[/start] Attempting to send error message to channel (not ephemeral).")
                    await interaction.channel.send(f"{interaction.user.mention}, an unexpected critical error occurred. Please try again later or contact support.")
            except Exception as send_e:
                logger.error(f"[/start] Failed to send error message to user after critical error: {send_e}", exc_info=True)


async def setup(bot: NyxaBot):
    await bot.add_cog(Start(bot))