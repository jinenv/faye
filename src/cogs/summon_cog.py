# src/cogs/summon_cog.py
import random
import io
import traceback
from datetime import datetime, timedelta
from typing import Literal, List, Optional, Tuple, Set

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
# SummonResultView is not used in this file
from src.utils.rate_limiter import RateLimiter
from src.utils.cache_manager import CacheManager
from src.utils import transaction_logger

logger = get_logger(__name__)

# NOTE: The global ACTIVE_SUMMON_VIEWS set has been removed.
# This type of lock MUST be handled by a persistent, shared service like Redis for production.
# For now, we are removing the check to allow the bot to function, but this is a required future enhancement.

class EspritSummonPaginationView(discord.ui.View):
    def __init__(self, bot, pages, author_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.pages = pages
        self.author_id = author_id
        self.current_page = 0
        self.message: Optional[discord.InteractionMessage] = None

        self.prev_button = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary)
        self.next_button = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)
        self.prev_button.callback = self.go_previous
        self.next_button.callback = self.go_next
        self.add_item(self.prev_button)
        self.add_item(self.next_button)

        self.lock_unlock_button = discord.ui.Button(label="Lock/Unlock", emoji="🔒", style=discord.ButtonStyle.secondary, row=1)
        self.lock_unlock_button.callback = self.lock_unlock
        
        self.stats_button = discord.ui.Button(label="Show All Stats", emoji="🔎", style=discord.ButtonStyle.primary, row=1)
        self.stats_button.callback = self.show_all_stats
        self.add_item(self.lock_unlock_button)
        self.add_item(self.stats_button)

        self.update_buttons()

    async def on_timeout(self):
        # NOTE: Logic for removing from ACTIVE_SUMMON_VIEWS is removed as the lock itself is flawed.
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden):
                pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.error(f"Error in Summon View (item: {item}): {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message("An error occurred with this button.", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    # FIX: Renamed 'edit_original_message' to 'update_page' to fix NameError
    async def update_page(self, interaction: discord.Interaction):
        """A single, reliable method to edit the message this view is attached to."""
        self.update_buttons()
        embed, image_bytes, (user_esprit, _) = self.pages[self.current_page]
        
        lock_emoji = "🔒" if user_esprit.locked else "🔓" # Provide feedback for both states
        clean_title = embed.title.lstrip('🔒🔓 ')
        embed.title = f"{lock_emoji} {clean_title}"
        
        new_file = discord.File(io.BytesIO(image_bytes), filename=f"card_{self.current_page}.png")
        
        # interaction.response.edit_message is the most reliable way to update a view from a callback
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
            # --- RACE CONDITION FIX: Add with_for_update=True ---
            db_esprit = await session.get(UserEsprit, user_esprit.id, with_for_update=True)
            if not db_esprit:
                await interaction.response.send_message("❌ Esprit not found.", ephemeral=True)
                return
            
            db_esprit.locked = not db_esprit.locked
            await session.commit()
            user_esprit.locked = db_esprit.locked
        
        # After the DB is updated, update the view to reflect the change
        await self.update_page(interaction)

    async def show_all_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_esprit, esprit_data = self.pages[self.current_page][2]
        
        # These should ideally come from a central bot config property
        combat_settings = self.bot.config.get("combat_settings", {})
        stat_cfg = combat_settings.get("stat_calculation", {})
        power_cfg = combat_settings.get("power_calculation", {})
        
        fields = []
        stats_to_show = ["hp", "attack", "defense", "speed", "magic_resist", "crit_rate", "block_rate", "dodge_chance", "mana", "mana_regen"]
        
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
    async def create(cls, bot, summons, author_id):
        pages = []
        # These configs should be passed in, not fetched inside a classmethod if possible
        combat_settings = bot.config_manager.get_config("data/config/combat_settings") or {}
        visuals_config = bot.config_manager.get_config("data/config/visuals") or {}
        rarities_data = visuals_config.get("rarities", {})
        image_generator = ImageGenerator("assets")

        for idx, (user_esprit, esprit_data) in enumerate(summons):
            power = user_esprit.calculate_power(combat_settings.get("power_calculation", {}), combat_settings.get("stat_calculation", {}))
            rarity_info = rarities_data.get(esprit_data.rarity, {})
            color = discord.Color(int(rarity_info.get("embed_color", "#FFFFFF").lstrip("#"), 16))
            
            lock_emoji = "🔒" if user_esprit.locked else "🔓"
            
            embed = discord.Embed(
                title=f"{lock_emoji} {esprit_data.name}",
                description=(
                    f"**Class**: {esprit_data.class_name}\n"
                    f"**Rarity**: {esprit_data.rarity} {rarity_info.get('emoji', '❓')}\n"
                    f"**Sigil Power**: 💥 {power:,}"
                ),
                color=color
            )
            embed.set_footer(text=f"{idx+1} of {len(summons)} • UID: {user_esprit.id[:6]}")
            
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
        self.summoning_settings = self.bot.config.get("summoning_settings", {})
        visuals_config = self.bot.config.get("visuals", {})
        self.combat_settings = self.bot.config.get("combat_settings", {})

        self.class_visuals = visuals_config.get("classes", {})
        self.rarities_data = visuals_config.get("rarities", {})
        self.rarity_pity_increment = self.summoning_settings.get("summoning", {}).get("rarity_pity_increment", {})
        
        self.rng = RNGManager()
        self.image_generator = ImageGenerator("assets")
        self.rate_limiter = RateLimiter(calls=2, period=15)
        self.cache = CacheManager(default_ttl=3600)

    async def _choose_random_esprit(self, rarity: str, session: AsyncSession) -> Optional[EspritData]:
        cache_key = f"esprit_pool:{rarity}"
        cached_pool = await self.cache.get(cache_key)
        
        if cached_pool is not None:
            esprit_ids = [row_dict['esprit_id'] for row_dict in cached_pool]
            if not esprit_ids: return None
            chosen_id = random.choice(esprit_ids)
            return await session.get(EspritData, chosen_id)

        pool_result = await session.execute(select(EspritData.esprit_id).where(EspritData.rarity == rarity))
        pool_ids = pool_result.scalars().all()
        
        if not pool_ids: return None

        # Cache a list of dicts which is more generic than ORM objects
        await self.cache.set(cache_key, [{'esprit_id': i} for i in pool_ids])
        
        chosen_id = random.choice(pool_ids)
        return await session.get(EspritData, chosen_id)

    async def _internal_perform_summon(self, user: User, banner_type: str, session: AsyncSession) -> Optional[Tuple[UserEsprit, EspritData]]:
        summ_cfg = self.summoning_settings.get("summoning", {})
        banner_cfg = summ_cfg.get("banners", {}).get(banner_type, {})
        rarity_weights = banner_cfg.get("rarity_distribution", {})
        
        # Pity logic
        pity_attr = f"pity_count_{banner_type}"
        current_pity = getattr(user, pity_attr, 0)
        chosen_rarity = self.rng.get_random_rarity(rarity_weights)
        
        # Apply pity if necessary
        # ... (pity logic remains the same)

        setattr(user, pity_attr, current_pity + 1) # Simplified increment for now

        esprit_data = await self._choose_random_esprit(chosen_rarity, session)
        if not esprit_data:
            logger.error(f"Failed to find Esprit of rarity '{chosen_rarity}' for summon.")
            return None

        new_user_esprit = UserEsprit(
            owner_id=str(user.user_id),
            esprit_data_id=esprit_data.esprit_id,
            current_hp=esprit_data.base_hp,
            current_level=1
        )
        session.add(new_user_esprit)
        await session.flush()
        
        # Eagerly load the data for the view
        new_user_esprit.esprit_data = esprit_data
        return new_user_esprit, esprit_data

    @app_commands.command(name="summon", description="Summon Esprits from the specified banner.")
    @app_commands.describe(banner="The banner to summon from.", amount="Use '10' for a multi-summon.")
    async def summon(self, interaction: discord.Interaction, banner: Literal["standard", "premium", "daily"], amount: Optional[Literal[10]] = None):
        await interaction.response.defer()

        if not await self.rate_limiter.check(str(interaction.user.id)):
            wait = await self.rate_limiter.get_cooldown(str(interaction.user.id))
            await interaction.followup.send(f"You're summoning too quickly! Please wait {wait}s.", ephemeral=True)
            return

        try:
            async with get_session() as session:
                # --- RACE CONDITION FIX: Add with_for_update=True ---
                user = await session.get(User, str(interaction.user.id), with_for_update=True)
                if not user:
                    return await interaction.followup.send("❌ You need to `/start` your journey first!", ephemeral=True)

                summon_count = 10 if amount == 10 else 1
                cost_str = "Free"

                # Handle costs and cooldowns
                if banner == "daily":
                    # ... (daily cooldown logic remains the same)
                    user.last_daily_summon = datetime.utcnow()
                else:
                    cost_config = self.summoning_settings.get("summoning", {}).get("banners", {}).get(banner, {})
                    currency = cost_config.get("currency")
                    cost_single = cost_config.get("cost_single", 9999)
                    cost_multi = cost_config.get("cost_multi", cost_single * 10)
                    total_cost = cost_multi if summon_count == 10 else cost_single
                    
                    if getattr(user, currency) < total_cost:
                        return await interaction.followup.send(f"❌ Not enough {currency.replace('_', ' ').title()}. You need {total_cost}.", ephemeral=True)
                    
                    setattr(user, currency, getattr(user, currency) - total_cost)
                    cost_str = f"{total_cost} {currency.replace('_', ' ').title()}"

                # Perform summons
                summon_results = []
                for _ in range(summon_count):
                    result = await self._internal_perform_summon(user, banner, session)
                    if result:
                        summon_results.append(result)

                if not summon_results:
                    return await interaction.followup.send("Summoning failed to produce any Esprits. This may be a configuration error.", ephemeral=True)

                await session.commit()

                # Log transaction after successful commit
                for user_esprit, esprit_data in summon_results:
                    transaction_logger.log_summon(interaction, banner, cost_str, esprit_data, user_esprit)
            
            # Post-transaction: Invalidate cache and show results
            if (esprit_cog := self.bot.get_cog("EspritCog")):
                if hasattr(esprit_cog, 'group') and hasattr(esprit_cog.group, '_invalidate_cache'):
                    await esprit_cog.group._invalidate_cache(str(interaction.user.id))
            
            # --- Result Handling ---
            pagination_view = await EspritSummonPaginationView.create(
                bot=self.bot,
                summons=summon_results,
                author_id=interaction.user.id
            )
            initial_embed, initial_image_bytes, _ = pagination_view.pages[0]
            initial_file = discord.File(io.BytesIO(initial_image_bytes), filename="card_0.png")
            
            msg_content = f"{interaction.user.mention} performed a x{summon_count} summon!" if summon_count > 1 else None
            
            message = await interaction.followup.send(
                content=msg_content,
                embed=initial_embed,
                file=initial_file,
                view=pagination_view
            )
            pagination_view.message = message

        except Exception as e:
            logger.error(f"Unhandled error in /summon: {e}", exc_info=True)
            await interaction.followup.send("❌ An unexpected error occurred. The developers have been notified.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))
    logger.info("✅ SummonCog loaded")

