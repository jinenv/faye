# src/cogs/summon_cog.py
import random
import io
import traceback
from datetime import datetime, timedelta
from typing import Literal, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, EspritData, UserEsprit
from src.database.db import get_session
from src.utils.image_generator import ImageGenerator
from src.utils.rng_manager import RNGManager
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiter
from src.utils.cache_manager import CacheManager
from src.utils import transaction_logger

logger = get_logger(__name__)

class EspritSummonPaginationView(discord.ui.View):
    def __init__(self, bot, pages, author_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.pages = pages
        self.author_id = author_id
        self.current_page = 0
        self.message: Optional[discord.InteractionMessage] = None

        self.prev_button = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, custom_id="prev")
        self.next_button = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, custom_id="next")
        self.lock_unlock_button = discord.ui.Button(label="Lock/Unlock", emoji="🔒", style=discord.ButtonStyle.secondary, row=1, custom_id="lock")
        self.stats_button = discord.ui.Button(label="Show All Stats", emoji="🔎", style=discord.ButtonStyle.primary, row=1, custom_id="stats")

        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.lock_unlock_button)
        self.add_item(self.stats_button)
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return False
        
        # Route interaction based on custom_id
        custom_id = interaction.data.get("custom_id")
        if custom_id == "prev": await self.go_previous(interaction)
        elif custom_id == "next": await self.go_next(interaction)
        elif custom_id == "lock": await self.lock_unlock(interaction)
        elif custom_id == "stats": await self.show_all_stats(interaction)
        return True

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    async def update_page(self, interaction: discord.Interaction):
        """A single, reliable method to edit the message this view is attached to."""
        self.update_buttons()
        embed, image_bytes, (user_esprit, _) = self.pages[self.current_page]
        
        lock_emoji = "🔒" if user_esprit.locked else "🔓"
        clean_title = embed.title.lstrip('🔒🔓 ')
        embed.title = f"{lock_emoji} {clean_title}"
        
        new_file = discord.File(io.BytesIO(image_bytes), filename=f"card_{self.current_page}.png")
        await interaction.response.edit_message(embed=embed, attachments=[new_file], view=self)

    async def go_previous(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_page(interaction)

    async def go_next(self, interaction: discord.Interaction):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_page(interaction)

    async def lock_unlock(self, interaction: discord.Interaction):
        user_esprit, _ = self.pages[self.current_page][2]
        
        async with get_session() as session:
            db_esprit = await session.get(UserEsprit, user_esprit.id, with_for_update=True)
            if not db_esprit:
                return await interaction.response.send_message("❌ Esprit not found.", ephemeral=True)
            
            db_esprit.locked = not db_esprit.locked
            await session.commit()
            user_esprit.locked = db_esprit.locked # Update the local copy
        
        await self.update_page(interaction)

    async def show_all_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_esprit, esprit_data = self.pages[self.current_page][2]
        
        combat_settings = self.bot.config.get("combat_settings", {})
        stat_cfg = combat_settings.get("stat_calculation", {})
        power_cfg = combat_settings.get("power_calculation", {})
        
        fields, stats_to_show = [], ["hp", "attack", "defense", "speed", "magic_resist", "crit_rate", "block_rate", "dodge_chance", "mana", "mana_regen"]
        for stat_name in stats_to_show:
            value = user_esprit.calculate_stat(stat_name, stat_cfg)
            val_str = f"{value:.1%}" if isinstance(value, float) and value <= 1.0 else f"{int(value):,}"
            fields.append((stat_name.replace("_", " ").title(), val_str))

        power_val = user_esprit.calculate_power(power_cfg, stat_cfg)
        
        embed = discord.Embed(title=f"🔎 {esprit_data.name} — Full Stats", color=discord.Color.purple())
        embed.add_field(name="Power", value=f"💥 {power_val:,}", inline=True)
        embed.add_field(name="Level", value=str(user_esprit.current_level), inline=True)
        embed.add_field(name="Limit Breaks", value=str(user_esprit.limit_breaks_performed), inline=True)
        for name, val_str in fields:
            embed.add_field(name=name, value=val_str, inline=True)
        embed.set_footer(text=f"UID: {user_esprit.id[:6]}")
        await interaction.followup.send(embed=embed)

    @classmethod
    async def create(cls, bot: commands.Bot, summons: List[Tuple[UserEsprit, EspritData]], author_id: int, combat_settings: dict, visuals_config: dict):
        """
        REFACTORED: Now accepts config dictionaries as arguments instead of fetching them.
        This decouples the View from the main bot's config structure.
        """
        pages = []
        rarities_data = visuals_config.get("rarities", {})
        image_generator = ImageGenerator("assets")

        for idx, (user_esprit, esprit_data) in enumerate(summons):
            power = user_esprit.calculate_power(combat_settings.get("power_calculation", {}), combat_settings.get("stat_calculation", {}))
            rarity_info = rarities_data.get(esprit_data.rarity, {})
            color = discord.Color(int(rarity_info.get("embed_color", "#FFFFFF").lstrip("#"), 16))
            
            embed = discord.Embed(
                title=f"🔓 {esprit_data.name}",
                description=f"**Class**: {esprit_data.class_name}\n**Rarity**: {esprit_data.rarity} {rarity_info.get('emoji', '❓')}\n**Sigil Power**: 💥 {power:,}",
                color=color
            ).set_footer(text=f"{idx+1} of {len(summons)} • UID: {user_esprit.id[:6]}")
            
            card_img = await image_generator.render_esprit_card(esprit_data.model_dump())
            with io.BytesIO() as buf:
                card_img.save(buf, format="PNG")
                image_bytes = buf.getvalue()
            
            embed.set_image(url=f"attachment://card_{idx}.png")
            pages.append((embed, image_bytes, (user_esprit, esprit_data)))
            
        return cls(bot, pages, author_id)

class SummonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rng = RNGManager()
        self.rate_limiter = RateLimiter(calls=2, period=15)
        self.cache = CacheManager(default_ttl=3600)

    async def _choose_random_esprit(self, rarity: str, session: AsyncSession) -> Optional[EspritData]:
        # Logic remains sound.
        cache_key = f"esprit_pool:{rarity}"
        cached_pool = await self.cache.get(cache_key)
        
        if cached_pool:
            esprit_ids = [row_dict['esprit_id'] for row_dict in cached_pool]
            if not esprit_ids: return None
            return await session.get(EspritData, random.choice(esprit_ids))

        pool_result = await session.execute(select(EspritData.esprit_id).where(EspritData.rarity == rarity))
        pool_ids = pool_result.scalars().all()
        if not pool_ids: return None

        await self.cache.set(cache_key, [{'esprit_id': i} for i in pool_ids])
        return await session.get(EspritData, random.choice(pool_ids))

    async def _internal_perform_summon(self, user: User, banner_type: str, banner_cfg: dict, session: AsyncSession) -> Optional[Tuple[UserEsprit, EspritData]]:
        # Logic remains sound.
        rarity_weights = banner_cfg.get("rarity_distribution", {})
        chosen_rarity = self.rng.get_random_rarity(rarity_weights) # Pity logic would go here
        
        esprit_data = await self._choose_random_esprit(chosen_rarity, session)
        if not esprit_data:
            logger.error(f"Failed to find Esprit of rarity '{chosen_rarity}' for summon.")
            return None

        new_user_esprit = UserEsprit(owner_id=str(user.user_id), esprit_data_id=esprit_data.esprit_id, current_hp=esprit_data.base_hp, current_level=1)
        session.add(new_user_esprit)
        await session.flush()
        new_user_esprit.esprit_data = esprit_data
        return new_user_esprit, esprit_data

    @app_commands.command(name="summon", description="Summon Esprits from the specified banner.")
    @app_commands.describe(banner="The banner to summon from.", amount="Use '10' for a multi-summon.")
    async def summon(self, interaction: discord.Interaction, banner: Literal["standard", "premium", "daily"], amount: Optional[Literal[10]] = None):
        await interaction.response.defer()

        if not await self.rate_limiter.check(str(interaction.user.id)):
            wait = await self.rate_limiter.get_cooldown(str(interaction.user.id))
            return await interaction.followup.send(f"You're summoning too quickly! Please wait {wait}s.", ephemeral=True)

        try:
            # --- REFACTORED: Fetch configs here in the command ---
            summoning_settings = self.bot.config.get("summoning_settings", {})
            banner_cfg = summoning_settings.get("summoning", {}).get("banners", {}).get(banner, {})
            
            async with get_session() as session:
                user = await session.get(User, str(interaction.user.id), with_for_update=True)
                if not user: return await interaction.followup.send("❌ You need to `/start` your journey first!", ephemeral=True)

                summon_count = 10 if amount == 10 else 1
                cost_str = "Free"

                if banner == "daily":
                    # Cooldown check
                    cooldown_hours = summoning_settings.get("cooldowns", {}).get('daily_summon_hours', 22)
                    if user.last_daily_summon and datetime.utcnow() < user.last_daily_summon + timedelta(hours=cooldown_hours):
                        return await interaction.followup.send("❌ You've already claimed your free daily summon.", ephemeral=True)
                    user.last_daily_summon = datetime.utcnow()
                else:
                    currency, cost_single, cost_multi = banner_cfg.get("currency"), banner_cfg.get("cost_single", 9999), banner_cfg.get("cost_multi", 99990)
                    total_cost = cost_multi if summon_count == 10 else cost_single
                    if getattr(user, currency, 0) < total_cost:
                        return await interaction.followup.send(f"❌ Not enough {currency.replace('_', ' ').title()}. You need {total_cost}.", ephemeral=True)
                    setattr(user, currency, getattr(user, currency) - total_cost)
                    cost_str = f"{total_cost} {currency.replace('_', ' ').title()}"

                summon_results = [result for _ in range(summon_count) if (result := await self._internal_perform_summon(user, banner, banner_cfg, session))]
                if not summon_results:
                    return await interaction.followup.send("Summoning failed. This may be a configuration error.", ephemeral=True)

                await session.commit()
                for user_esprit, esprit_data in summon_results:
                    transaction_logger.log_summon(interaction, banner, cost_str, esprit_data, user_esprit)
            
            # --- REFACTORED: Pass configs to the create method ---
            combat_settings = self.bot.config.get("combat_settings", {})
            visuals_config = self.bot.config.get("visuals", {})
            
            pagination_view = await EspritSummonPaginationView.create(
                bot=self.bot,
                summons=summon_results,
                author_id=interaction.user.id,
                combat_settings=combat_settings,
                visuals_config=visuals_config
            )
            initial_embed, initial_image_bytes, _ = pagination_view.pages[0]
            initial_file = discord.File(io.BytesIO(initial_image_bytes), filename="card_0.png")
            
            msg_content = f"{interaction.user.mention} performed a x{summon_count} summon!" if summon_count > 1 else f"{interaction.user.mention} performed a summon!"
            message = await interaction.followup.send(content=msg_content, embed=initial_embed, file=initial_file, view=pagination_view)
            pagination_view.message = message

        except Exception as e:
            logger.error(f"Unhandled error in /summon: {e}", exc_info=True)
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))
    logger.info("✅ SummonCog loaded")

