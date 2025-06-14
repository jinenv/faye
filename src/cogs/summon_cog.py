# src/cogs/summon_cog.py
import random
import io
from datetime import datetime, timedelta
from typing import Literal, List

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
# --- 1. IMPORT NEW DEPENDENCIES ---
from src.utils.rate_limiter import RateLimiter
from src.utils.cache_manager import CacheManager
from src.utils import transaction_logger


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
        
        self.rarity_pity_increment = (
            self.game_settings.get("summoning", {}).get("rarity_pity_increment", {})
        )

        self.rng = RNGManager()
        self.image_generator = ImageGenerator(self.assets_base)
        
        # --- 2. INITIALIZE UTILS ---
        self.rate_limiter = RateLimiter(calls=5, period=10)  # Allow 5 summons every 10 seconds
        self.cache = CacheManager(default_ttl=3600)  # Cache Esprit pools for 1 hour

    # --- 3. ADD CACHE INVALIDATION METHOD ---
    async def invalidate_esprit_pools_cache(self):
        """Invalidates the cached Esprit pools. Called by admin cog on reload."""
        await self.cache.clear_pattern("esprit_pool:")
        logger.info("Esprit summoning pools cache invalidated.")

    def _get_rarity_color(self, rarity_name: str) -> discord.Color:
        hex_color = (self.rarity_visuals.get(rarity_name) or {}).get("border_color", "#FFFFFF")
        return discord.Color(int(hex_color.lstrip("#"), 16))

    def _create_pity_bar(self, current: int, maximum: int) -> str:
        if maximum == 0:
            return "[Pity N/A]"
        pct = min(100, current * 100 / maximum)
        bar_len = 10
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "─" * (bar_len - filled)
        return f"[{bar}] {pct:.0f}%"

    # --- 4. UPDATE HELPER TO USE CACHE ---
    async def _choose_random_esprit(self, rarity: str, session: AsyncSession) -> EspritData | None:
        cache_key = f"esprit_pool:{rarity}"
        
        # Try to get the pool from cache first
        cached_pool = await self.cache.get(cache_key)
        if cached_pool is not None:
            return random.choice(cached_pool) if cached_pool else None

        # If not in cache, query the database
        pool: List[EspritData] = (
            (await session.execute(select(EspritData).where(EspritData.rarity == rarity)))
            .scalars()
            .all()
        )
        
        # Store the result in cache for next time
        await self.cache.set(cache_key, pool)
        
        return random.choice(pool) if pool else None

    async def perform_summon(
        self,
        interaction: discord.Interaction,
        user: User,
        banner_type: str,
        session: AsyncSession,
    ):
        summ_cfg = self.game_settings["summoning"]
        banner_cfg = summ_cfg["banners"][banner_type]
        rarity_weights = banner_cfg["rarity_distribution"]
        # Use the pity guarantee from the directive
        max_pity = summ_cfg.get("pity_system_guarantee_after", 100)

        pity_attr = f"pity_count_{banner_type}"
        current_pity = getattr(user, pity_attr, 0)
        
        chosen_rarity = self.rng.get_random_rarity(rarity_weights)
        
        increment = self.rarity_pity_increment.get(chosen_rarity, 1)
        new_pity = current_pity + increment

        # Logic from directive: guarantee Epic if pity is met and roll was below Epic
        if new_pity >= max_pity:
            rarity_order = ["Common", "Uncommon", "Rare", "Epic"]
            if chosen_rarity in rarity_order:
                 chosen_rarity = "Epic" 
            new_pity = 0

        setattr(user, pity_attr, new_pity)

        esprit_data = await self._choose_random_esprit(chosen_rarity, session)
        if not esprit_data:
            setattr(user, pity_attr, current_pity)  # revert on failure
            return await interaction.followup.send(f"No Esprits of rarity '{chosen_rarity}' found.", ephemeral=True)

        new_user_esprit = UserEsprit(
            owner_id=str(user.user_id),
            esprit_data_id=esprit_data.esprit_id,
            current_hp=esprit_data.base_hp,
            current_level=1
        )
        new_user_esprit.esprit_data = esprit_data
        session.add(new_user_esprit)
        await session.flush()
        await session.refresh(new_user_esprit)
        
        # Pass configs to power calculation
        power = new_user_esprit.calculate_power(
            self.game_settings.get("power_calculation", {}),
            self.game_settings.get("stat_calculation", {})
        )
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
        embed.set_footer(text=f"UID: {new_user_esprit.id}")

        card_pil = await self.image_generator.render_esprit_card(esprit_data.model_dump())
        with io.BytesIO() as buf:
            card_pil.save(buf, "PNG")
            file = discord.File(io.BytesIO(buf.getvalue()), filename="esprit_card.png")
        embed.set_image(url="attachment://esprit_card.png")

        view = SummonResultView(new_user_esprit, self.bot)
        await interaction.followup.send(embed=embed, file=file, view=view)
        
        # Return the created Esprit and its data for logging
        return new_user_esprit, esprit_data

    @app_commands.command(name="summon", description="Summon an Esprit from the specified banner.")
    @app_commands.describe(banner="Banner to summon from.")
    async def summon(self, interaction: discord.Interaction, banner: Literal["standard", "premium", "daily"]):
        await interaction.response.defer(ephemeral=True)

        # --- 5. ADD RATE LIMITING CHECK ---
        if not await self.rate_limiter.check(interaction.user.id):
            return await interaction.followup.send("You're summoning too quickly! Please wait a moment.", ephemeral=True)

        async with get_session() as session:
            user = await session.get(User, str(interaction.user.id))
            if not user:
                return await interaction.followup.send("❌ You need to `/start` your journey first!", ephemeral=True)

            cost_str = "Free"
            summon_result = None

            if banner == "standard":
                cost = self.game_settings["summoning"]["banners"]["standard"]["cost_single"]
                if user.azurites < cost:
                    return await interaction.followup.send(f"❌ Not enough Azurites. Need {cost}.", ephemeral=True)
                user.azurites -= cost
                cost_str = f"{cost} Azurites"
                summon_result = await self.perform_summon(interaction, user, "standard", session)

            elif banner == "premium":
                cost = self.game_settings["summoning"]["banners"]["premium"]["cost_single"]
                if user.aether < cost:
                    return await interaction.followup.send(f"❌ Not enough Aether. Need {cost}.", ephemeral=True)
                user.aether -= cost
                cost_str = f"{cost} Aether"
                summon_result = await self.perform_summon(interaction, user, "premium", session)

            else:  # daily
                hours_cd = self.game_settings["cooldowns"]["daily_summon_hours"]
                if user.last_daily_summon and datetime.utcnow() < user.last_daily_summon + timedelta(hours=hours_cd):
                    remaining = user.last_daily_summon + timedelta(hours=hours_cd) - datetime.utcnow()
                    h, rem = divmod(int(remaining.total_seconds()), 3600)
                    m, _ = divmod(rem, 60)
                    return await interaction.followup.send(f"⏳ Daily summon on cooldown. Try again in **{h}h {m}m**.", ephemeral=True)
                user.last_daily_summon = datetime.utcnow()
                summon_result = await self.perform_summon(interaction, user, "standard", session)

            if summon_result:
                await session.commit()
                # --- 6. CALL TRANSACTION LOGGER ---
                user_esprit, esprit_data = summon_result
                transaction_logger.log_summon(interaction, banner, cost_str, esprit_data, user_esprit)

                if (esprit_cog := self.bot.get_cog("EspritCog")):
                    await esprit_cog.group._invalidate(str(interaction.user.id))
            else:
                # If perform_summon failed, the session will just close without committing.
                logger.warning(f"Summon failed for user {interaction.user.id} on banner {banner}, no transaction was committed.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))
    logger.info("✅ SummonCog loaded")