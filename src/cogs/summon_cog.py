# src/cogs/summon_cog.py
import random
import io
from datetime import datetime, timedelta
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, EspritData, UserEsprit
from src.database.db import get_session
from src.utils.image_generator import ImageGenerator
from src.utils.rng_manager import RNGManager
from src.utils.logger import get_logger
from src.views.summon_result import SummonResultView

logger = get_logger(__name__)


class SummonCog(commands.Cog):
    """Handles all Esprit summoning-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.assets_base = "assets"

        cfg = self.bot.config_manager
        self.class_visuals = cfg.get_config("data/config/class_visuals") or {}
        self.rarity_visuals = cfg.get_config("data/config/rarity_visuals") or {}
        self.game_settings = cfg.get_config("data/config/game_settings") or {}

        # pity-point table comes from config; fall back if missing
        self.rarity_pity_increment = (
            self.game_settings["summoning"].get("rarity_pity_increment") or {
                "Common": 1, "Uncommon": 2, "Rare": 3,
                "Epic": 6, "Celestial": 8, "Supreme": 10, "Deity": 12,
            }
        )

        self.rng = RNGManager()
        self.image_generator = ImageGenerator(self.assets_base)

    # ── helpers ──────────────────────────────────────────────────────────
    def _get_rarity_color(self, rarity_name: str) -> discord.Color:
        hex_color = (self.rarity_visuals.get(rarity_name) or {}).get(
            "border_color", "#FFFFFF"
        )
        return discord.Color(int(hex_color.lstrip("#"), 16))

    def _create_pity_bar(self, current: int, maximum: int) -> str:
        """Returns a 10-char bar plus percentage (e.g., [█████─────] 50%)."""
        if maximum == 0:
            return "[Pity N/A]"
        pct = min(100, current * 100 / maximum)
        bar_len = 10
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "─" * (bar_len - filled)
        return f"[{bar}] {pct:.0f}%"

    async def _choose_random_esprit(
        self, rarity: str, session: AsyncSession
    ) -> EspritData | None:
        pool = (
            (await session.execute(select(EspritData).where(EspritData.rarity == rarity)))
            .scalars()
            .all()
        )
        return random.choice(pool) if pool else None

    # ── summon core ───────────────────────────────────────────────────────
    async def perform_summon(
        self,
        interaction: discord.Interaction,
        user: User,
        banner_type: str,
        session: AsyncSession,
    ):
        """Performs one summon and sends the result embed."""
        summ_cfg = self.game_settings["summoning"]
        banner_cfg = summ_cfg["banners"][banner_type]
        rarity_weights = banner_cfg["rarity_distribution"]
        max_pity = summ_cfg["pity_system_guarantee_after"]

        pity_attr = f"pity_count_{banner_type}"
        current_pity = getattr(user, pity_attr, 0)

        # 1) roll rarity
        chosen_rarity = self.rng.get_random_rarity(rarity_weights)

        # 2) add pity based on rarity
        increment = self.rarity_pity_increment.get(chosen_rarity, 1)
        new_pity = current_pity + increment

        # 3) guarantee if bar filled
        if new_pity >= max_pity:
            chosen_rarity = "Supreme"      # tweak to Celestial/Supreme if you want
            new_pity = 0

        setattr(user, pity_attr, new_pity)

        # 4) fetch data
        esprit_data = await self._choose_random_esprit(chosen_rarity, session)
        if not esprit_data:
            setattr(user, pity_attr, current_pity)  # revert on failure
            return await interaction.followup.send(
                f"No Esprits of rarity '{chosen_rarity}' found.", ephemeral=True
            )

        # 5) create UserEsprit row
        new_user_esprit = UserEsprit(
            owner_id=str(user.user_id),
            esprit_data_id=esprit_data.esprit_id,
            current_hp=esprit_data.base_hp,
            current_level=1,
            current_xp=0,
        )
        new_user_esprit.esprit_data = esprit_data
        session.add(new_user_esprit)
        await session.flush()
        await session.refresh(new_user_esprit)

        # ── embed ────────────────────────────────────────────────────────
        power = new_user_esprit.calculate_power()
        emoji = self.class_visuals.get(esprit_data.class_name, "❓")
        pity_bar = self._create_pity_bar(new_pity, max_pity)

        embed = discord.Embed(
            description=(
                f"{emoji} **{esprit_data.class_name}**\n"
                f"**{esprit_data.rarity}** | Sigil: 💥 **{power}**\n\n"
                f"{pity_bar}"
            ),
            color=self._get_rarity_color(chosen_rarity),
        )
        embed.set_footer(text=f"{new_user_esprit.id}")

        # attach generated card image
        card_pil = self.image_generator.render_esprit_card(esprit_data.model_dump())
        with io.BytesIO() as buf:
            card_pil.save(buf, "PNG")
            file = discord.File(io.BytesIO(buf.getvalue()), filename="esprit_card.png")
        embed.set_image(url="attachment://esprit_card.png")

        view = SummonResultView(new_user_esprit, self.bot)
        await interaction.followup.send(embed=embed, file=file, view=view)

    # ── slash command ────────────────────────────────────────────────────
    @app_commands.command(
        name="summon", description="Summon an Esprit from the specified banner."
    )
    @app_commands.describe(banner="Banner to summon from.")
    async def summon(
        self,
        interaction: discord.Interaction,
        banner: Literal["standard", "premium", "daily"],
    ):
        await interaction.response.defer()

        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send(
                    "❌ You need to `/start` your journey first!", ephemeral=True
                )

            if banner == "standard":
                cost = self.game_settings["summoning"]["banners"]["standard"]["cost_single"]
                if user.azurites < cost:
                    return await interaction.followup.send(
                        f"❌ Not enough Azurites. Need {cost}.", ephemeral=True
                    )
                user.azurites -= cost
                await self.perform_summon(interaction, user, "standard", session)

            elif banner == "premium":
                cost = self.game_settings["summoning"]["banners"]["premium"]["cost_single"]
                if user.aether < cost:
                    return await interaction.followup.send(
                        f"❌ Not enough Aether. Need {cost}.", ephemeral=True
                    )
                user.aether -= cost
                await self.perform_summon(interaction, user, "premium", session)

            else:  # daily
                hours_cd = self.game_settings["cooldowns"]["daily_summon_hours"]
                if user.last_daily_summon and datetime.utcnow() < user.last_daily_summon + timedelta(hours=hours_cd):
                    remaining = user.last_daily_summon + timedelta(hours=hours_cd) - datetime.utcnow()
                    h, rem = divmod(int(remaining.total_seconds()), 3600)
                    m, _ = divmod(rem, 60)
                    return await interaction.followup.send(
                        f"⏳ Daily summon on cooldown. Try again in **{h}h {m}m**.",
                        ephemeral=True,
                    )
                user.last_daily_summon = datetime.utcnow()
                await self.perform_summon(interaction, user, "standard", session)

            # commit currency + pity + new esprit
            await session.commit()

        # invalidate cache so /esprit collection updates instantly
        if (esprit_cog := self.bot.get_cog("EspritCog")):
            await esprit_cog.group._invalidate(str(interaction.user.id))

async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))
    logger.info("✅ SummonCog loaded")