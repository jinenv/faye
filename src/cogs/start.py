# src/cogs/start.py

from __future__ import annotations
import random

import discord
from discord.ext import commands
from discord import app_commands
import sqlalchemy as sa
from sqlalchemy.future import select
import uuid

from ..bot import NyxaBot
from src.database.db import get_session
from src.database.models import User, EspritData, UserEsprit
from src.utils.config_manager import ConfigManager
from src.utils.image_generator import ImageGenerator
from src.utils.render_helpers import render_pil_to_discord_file
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Start(commands.Cog):
    def __init__(self, bot: NyxaBot):
        self.bot = bot
        self.config_manager = ConfigManager()
        self.image_generator = ImageGenerator()
        self.game_settings = self.config_manager.get_config("data/config/game_settings")
        # Note: game_settings.json must contain at least "starting_level" and "starting_gold"
        self.esprits_data = self.config_manager.get_config("data/config/esprits")

    @app_commands.command(
        name="start",
        description="Begin your adventure and summon your first Esprit!"
    )
    async def start(self, interaction: discord.Interaction):
        logger.info(f"[/start] Command received by {interaction.user.display_name} ({interaction.user.id}).")
        await interaction.response.defer(thinking=True)
        logger.info(f"[/start] Response deferred for {interaction.user.display_name}.")

        try:
            async with get_session() as session:
                logger.info(f"[/start] Database session obtained for {interaction.user.display_name}.")

                # 1. Check if user already exists
                user_query = select(User).where(User.user_id == str(interaction.user.id))
                user = (await session.execute(user_query)).scalar_one_or_none()
                logger.info(f"[/start] User exists: {user is not None}")

                if user:
                    await interaction.followup.send(
                        f"Welcome back, **{interaction.user.display_name}**! "
                        "You've already started your adventure. Use `/profile` to view your stats or `/explore` to continue!"
                    )
                    return

                # ── Pick a random starter Esprit ─────────────────────────────────
                starter_rarity_priority = ["Epic", "Rare", "Uncommon", "Common"]
                chosen_starter_esprit_id = None

                # Fetch all EspritData from the database
                all_db_esprits = await session.execute(select(EspritData))
                all_map = {e.esprit_id: e for e in all_db_esprits.scalars().all()}

                for rarity_tier in starter_rarity_priority:
                    eligible = [
                        (eid, obj) for eid, obj in all_map.items() if obj.rarity == rarity_tier
                    ]
                    if eligible:
                        chosen_starter_esprit_id = random.choice(eligible)[0]
                        logger.info(f"[/start] Chosen starter {chosen_starter_esprit_id} (rarity {rarity_tier})")
                        break

                if not chosen_starter_esprit_id:
                    await interaction.followup.send(
                        "Error: Could not determine a starter Esprit. Please contact an admin.",
                        ephemeral=True
                    )
                    logger.error("No eligible starter Esprits in DB.")
                    return

                # Fetch that EspritData
                stmt = select(EspritData).where(EspritData.esprit_id == chosen_starter_esprit_id)
                starter_obj = (await session.execute(stmt)).scalar_one_or_none()
                logger.info(f"[/start] Starter Esprit data: {starter_obj.name if starter_obj else 'None'}")

                if not starter_obj:
                    await interaction.followup.send(
                        f"Error: Starter Esprit '{chosen_starter_esprit_id}' not found in database.",
                        ephemeral=True
                    )
                    logger.error(f"Starter ID {chosen_starter_esprit_id} missing.")
                    return

                # 2. Create a new user
                new_user = User(
                    user_id=str(interaction.user.id),
                    username=interaction.user.name,
                    level=self.game_settings["starting_level"],
                    xp=0,
                    gold=self.game_settings["starting_gold"],
                    active_esprit_id=None
                )
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)
                logger.info(f"[/start] New user created: {new_user.username}")

                # 3. Create UserEsprit
                new_u_e = UserEsprit(
                    owner_id=new_user.user_id,
                    esprit_data_id=starter_obj.esprit_id,
                    current_hp=starter_obj.base_hp,
                    current_level=1,
                    current_xp=0
                )
                session.add(new_u_e)
                await session.commit()
                await session.refresh(new_u_e)
                logger.info(f"[/start] UserEsprit created: {new_u_e.id} ({starter_obj.name})")

                # 4. Update user's active_esprit_id
                new_user.active_esprit_id = new_u_e.id
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)
                logger.info(f"[/start] active_esprit_id set for user {new_user.username}")

                # 5. Generate the image
                summon_image_file = None
                try:
                    logger.info(f"[/start] Generating image for {starter_obj.name}")
                    # We convert the SQLAlchemy object to a dict so that render_esprit_detail_image can consume it
                    esprit_data_dict = starter_obj.to_dict()
                    summon_image_pil = await self.image_generator.render_esprit_detail_image(
                        esprit_data_dict=esprit_data_dict,
                        esprit_instance=new_u_e
                    )
                    summon_image_file = render_pil_to_discord_file(summon_image_pil, "summon_result.png")
                    logger.info("[/start] Image generated successfully.")
                except Exception as e:
                    logger.error(f"[/start] Error generating image: {e}", exc_info=True)
                    summon_image_file = None

                # 6. Send welcome message
                welcome_message = (
                    f"🎉 Welcome, **{interaction.user.display_name}**! Your adventure in Nyxa begins now!\n\n"
                    f"You've summoned your very first Esprit: **{starter_obj.name}**!\n"
                    f"This {starter_obj.rarity}-tier companion will aid you in your journey."
                )
                if summon_image_file:
                    await interaction.followup.send(content=welcome_message, file=summon_image_file)
                else:
                    await interaction.followup.send(content=welcome_message)
                logger.info("[/start] Sent initial followup.")

                # 7. Suggest next steps
                await interaction.channel.send(
                    f"**What's next, {interaction.user.display_name}?**\n\n"
                    "• Use `/explore` to send your Esprit on an adventure and earn rewards!\n"
                    "• Use `/profile` to check your stats and your Esprits.\n"
                    "• Once you have enough gold, try `/summon` to get more powerful Esprits!"
                )
                logger.info("[/start] Sent next‐steps message.")

        except Exception as e:
            logger.critical(f"[/start] Critical error: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.followup.send(
                    "A critical error occurred while starting your adventure. Please try again later.",
                    ephemeral=True
                )
            else:
                await interaction.channel.send(
                    f"{interaction.user.mention}, a critical error occurred. Please try again later."
                )


async def setup(bot: NyxaBot):
    await bot.add_cog(Start(bot))
