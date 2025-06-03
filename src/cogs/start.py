from __future__ import annotations
import random
import uuid

import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.future import select

from ..bot import NyxaBot
from src.database.db import get_session
from src.database.models import User, EspritData, UserEsprit
from src.utils.config_manager import ConfigManager
from src.utils.image_generator import ImageGenerator
from src.utils.render_helpers import render_pil_to_discord_file
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Start(commands.Cog):
    """/start – create profile & give first Esprit."""

    def __init__(self, bot: NyxaBot):
        self.bot = bot
        cfg = ConfigManager()
        self.image_gen = ImageGenerator()

        # note the full path ↓
        self.game_settings = cfg.get_config("data/config/game_settings") or {
            "starting_level": 1,
            "starting_gold": 500,
        }

    # ────────────────────────────────────────────────────────────────────
    @app_commands.command(name="start",
                          description="Begin your journey & receive a starter Esprit.")
    async def start(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        uid = str(interaction.user.id)

        async with get_session() as session:
            # already registered? -------------------------------------------------
            existing = (await session.execute(
                select(User).where(User.user_id == uid)
            )).scalar_one_or_none()

            if existing:
                await interaction.followup.send(
                    f"Welcome back, **{interaction.user.display_name}**! "
                    "Use `/profile` to view your stats."
                )
                return

            # pick starter (prefers Epic → Rare → …) ----------------------------
            all_esprits = (await session.execute(select(EspritData))).scalars().all()

            priority = ["Epic", "Rare", "Uncommon", "Common"]
            candidate = None
            for tier in priority:
                pool = [e for e in all_esprits if e.rarity == tier]
                if pool:
                    candidate = random.choice(pool)
                    break

            if not candidate:
                await interaction.followup.send(
                    "No starter esprits available. Contact an admin.", ephemeral=True
                )
                logger.critical("No EspritData rows in DB!")
                return

            # create DB rows -----------------------------------------------------
            new_usr = User(
                user_id=uid,
                username=interaction.user.name,
                level=self.game_settings["starting_level"],
                xp=0,
                gold=self.game_settings["starting_gold"],
            )
            session.add(new_usr)
            await session.commit()

            usr_esprit = UserEsprit(
                owner_id=new_usr.user_id,
                esprit_data_id=candidate.esprit_id,
                current_hp=candidate.base_hp,
                current_level=1,
                current_xp=0,
            )
            session.add(usr_esprit)
            await session.commit()

            new_usr.active_esprit_id = usr_esprit.id
            session.add(new_usr)
            await session.commit()

            # render fancy card ---------------------------------------------------
            try:
                pil = await self.image_gen.render_esprit_detail_image(
                    esprit_data=candidate.to_dict(),       # <- modern name
                    esprit_instance=usr_esprit,
                )
                file = render_pil_to_discord_file(pil, "starter.png")
            except Exception as e:
                logger.error("Card render failed: %s", e, exc_info=True)
                file = None

            # send messages -------------------------------------------------------
            blurb = (f"🎉 **{interaction.user.display_name}**, your journey begins!\n\n"
                     f"You’ve summoned **{candidate.name}** "
                     f"({candidate.rarity}). Take good care of them!")
            await interaction.followup.send(content=blurb, file=file) if file \
                else await interaction.followup.send(content=blurb)

            await interaction.channel.send(
                f"Next steps:\n"
                "• `/explore` – venture forth\n"
                "• `/profile` – check stats\n"
                "• `/summon` – get more Esprits"
            )


async def setup(bot: NyxaBot):
    await bot.add_cog(Start(bot))
