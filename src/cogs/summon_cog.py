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
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, EspritData, UserEsprit
from src.database.db import get_session
from src.utils.image_generator import ImageGenerator
from src.utils.rng_manager import RNGManager
from src.utils.logger import get_logger
from src.views.summon_result import SummonResultView
from src.utils.rate_limiter import RateLimiter
from src.utils.cache_manager import CacheManager
from src.utils import transaction_logger

logger = get_logger(__name__)

# Global set for lockout (move to a global utils if needed)
ACTIVE_SUMMON_VIEWS: Set[int] = set()

class EspritSummonPaginationView(discord.ui.View):
    def __init__(self, bot, pages, author_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.pages = pages  # Each page: (embed, image_bytes, (user_esprit, esprit_data))
        self.author_id = author_id
        self.current_page = 0
        self.message: Optional[discord.Message] = None

        # Navigation buttons
        self.prev_button = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary)
        self.next_button = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)
        self.prev_button.callback = self.go_previous
        self.next_button.callback = self.go_next
        self.add_item(self.prev_button)
        self.add_item(self.next_button)

        # Action buttons
        self.lock_unlock_button = discord.ui.Button(label="Lock/Unlock", emoji="🔒", style=discord.ButtonStyle.secondary, row=1)
        self.lock_unlock_button.callback = self.lock_unlock
        
        self.stats_button = discord.ui.Button(label="Show All Stats", emoji="🔎", style=discord.ButtonStyle.primary, row=1)
        self.stats_button.callback = self.show_all_stats
        self.add_item(self.lock_unlock_button)
        self.add_item(self.stats_button)

        self.update_buttons()

    async def on_timeout(self):
        ACTIVE_SUMMON_VIEWS.discard(self.author_id)
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                if self.message.channel.permissions_for(self.message.guild.me).send_messages:
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

    async def go_previous(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_page(interaction)

    async def go_next(self, interaction: discord.Interaction):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_page(interaction)

    async def edit_original_message(self, interaction: discord.Interaction):
        """A single, reliable method to edit the message this view is attached to."""
        self.update_buttons()
        embed, image_bytes, (user_esprit, _) = self.pages[self.current_page]
        
        lock_emoji = "🔒" if user_esprit.locked else ""
        clean_title = embed.title.lstrip('🔒 ')
        embed.title = f"{lock_emoji} {clean_title}"
        
        new_file = discord.File(io.BytesIO(image_bytes), filename=f"card_{self.current_page}.png")
        
        # Use interaction.message.edit() which is more stable for persistent views
        if interaction.message:
            await interaction.message.edit(embed=embed, attachments=[new_file], view=self)

    async def lock_unlock(self, interaction: discord.Interaction):
        await interaction.response.defer() # Acknowledge the click
        user_esprit, _ = self.pages[self.current_page][2]
        
        async with get_session() as session:
            db_esprit = await session.get(UserEsprit, user_esprit.id)
            if not db_esprit:
                await interaction.followup.send("❌ Esprit not found.", ephemeral=True)
                return
            
            db_esprit.locked = not db_esprit.locked
            await session.commit()
            user_esprit.locked = db_esprit.locked
        
        await self.edit_original_message(interaction)

    async def show_all_stats(self, interaction: discord.Interaction):
        # This method is correct. It sends a single, new ephemeral message.
        await interaction.response.defer(ephemeral=True)
        user_esprit, esprit_data = self.pages[self.current_page][2]
        combat_settings = self.bot.config_manager.get_config("data/config/combat_settings") or {}
        stat_cfg = combat_settings.get("stat_calculation", {})
        power_cfg = combat_settings.get("power_calculation", {})
        
        fields = []
        stats_to_show = ["hp", "attack", "defense", "speed", "magic_resist", "crit_rate", "block_rate", "dodge_chance", "mana", "mana_regen"]
        
        for stat_name in stats_to_show:
            is_base_stat = stat_name in ["crit_rate", "block_rate", "dodge_chance", "mana", "mana_regen"]
            value = getattr(esprit_data, f"base_{stat_name}", 0) if is_base_stat else user_esprit.calculate_stat(stat_name, stat_cfg)
            val_str = f"{value:.1%}" if isinstance(value, float) and value <= 1.0 else f"{value:,.0f}"
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
    async def create(cls, bot, summons, combat_settings, class_visuals, rarities_data, image_generator, author_id):
        pages = []
        for idx, (user_esprit, esprit_data) in enumerate(summons):
            power = user_esprit.calculate_power(
                combat_settings.get("power_calculation", {}),
                combat_settings.get("stat_calculation", {})
            )
            rarity = esprit_data.rarity
            rarity_data = rarities_data.get(rarity, {})
            emoji = rarity_data.get("emoji", "❓")
            
            color_hex = rarity_data.get("embed_color", "#FFFFFF")
            color = discord.Color(int(color_hex.lstrip("#"), 16))
            
            uid = str(user_esprit.id)[:6]
            lock_emoji = "🔒" if user_esprit.locked else ""
            
            embed = discord.Embed(
                title=f"{lock_emoji} {esprit_data.name}",
                description=(
                    f"**Class**: {esprit_data.class_name}\n"
                    f"**Rarity**: {rarity} {emoji}\n"
                    f"**Sigil Power**: 💥 {power:,}"
                ),
                color=color
            )
            embed.set_footer(text=f"{idx+1} of {len(summons)} • UID: {uid}")
            card = await image_generator.render_esprit_card(esprit_data.model_dump())
            buf = io.BytesIO()
            card.save(buf, format="PNG")
            image_bytes = buf.getvalue()
            embed.set_image(url=f"attachment://card_{idx}.png")
            pages.append((embed, image_bytes, (user_esprit, esprit_data)))
        return cls(bot, pages, author_id)

class SummonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = self.bot.config_manager
        self.summon_settings = cfg.get_config("data/config/summoning_settings") or {}
        visuals_config = cfg.get_config("data/config/visuals") or {}
        self.combat_settings = cfg.get_config("data/config/combat_settings") or {}
        self.class_visuals = visuals_config.get("classes", {})
        self.rarities_data = visuals_config.get("rarities", {})
        self.rarity_pity_increment = self.summon_settings.get("summoning", {}).get("rarity_pity_increment", {})
        self.rng = RNGManager()
        self.image_generator = ImageGenerator("assets")
        self.rate_limiter = RateLimiter(calls=5, period=10)
        self.cache = CacheManager(default_ttl=3600)

    async def invalidate_esprit_pools_cache(self):
        await self.cache.clear_pattern("esprit_pool:")
        logger.info("Esprit summoning pools cache invalidated.")

    def _get_rarity_color(self, rarity_name: str) -> discord.Color:
        rarity_data = self.rarities_data.get(rarity_name, {})
        hex_color = rarity_data.get("embed_color", "#FFFFFF") # Use embed_color
        return discord.Color(int(hex_color.lstrip("#"), 16))

    async def _choose_random_esprit(self, rarity: str, session: AsyncSession) -> Optional[EspritData]:
        cache_key = f"esprit_pool:{rarity}"
        cached_pool = await self.cache.get(cache_key)
        if cached_pool is not None:
            return random.choice(cached_pool) if cached_pool else None
        pool: List[EspritData] = ((await session.execute(select(EspritData).where(EspritData.rarity == rarity))).scalars().all())
        await self.cache.set(cache_key, pool)
        return random.choice(pool) if pool else None

    async def _internal_perform_summon(self, user: User, banner_type: str, session: AsyncSession) -> Optional[Tuple[UserEsprit, EspritData]]:
        summ_cfg = self.summon_settings["summoning"]
        banner_cfg = summ_cfg["banners"][banner_type]
        rarity_weights = banner_cfg["rarity_distribution"]
        max_pity = summ_cfg.get("pity_system_guarantee_after", 100)
        pity_attr = f"pity_count_{banner_type}"
        current_pity = getattr(user, pity_attr, 0)
        chosen_rarity = self.rng.get_random_rarity(rarity_weights)
        increment = self.rarity_pity_increment.get(chosen_rarity, 1)
        new_pity = current_pity + increment

        pity_reset_rarities = summ_cfg.get("pity_reset_rarities", ["Supreme", "Deity"])
        if chosen_rarity in pity_reset_rarities:
            new_pity = 0
            logger.info(f"User {user.user_id} pulled a {chosen_rarity}, resetting pity for {banner_type} banner.")
        elif new_pity >= max_pity:
            ALL_RARITIES = ["Common", "Uncommon", "Rare", "Epic", "Celestial", "Supreme", "Deity"]
            guaranteed_rarity = summ_cfg.get("pity_guarantee_rarity", "Epic")
            try:
                guaranteed_rank = ALL_RARITIES.index(guaranteed_rarity)
                chosen_rank = ALL_RARITIES.index(chosen_rarity)
                if chosen_rank < guaranteed_rank:
                    chosen_rarity = guaranteed_rarity
                new_pity = 0
            except ValueError:
                logger.warning("Rarity not in ALL_RARITIES list, pity system may fail.")

        setattr(user, pity_attr, new_pity)

        esprit_data = await self._choose_random_esprit(chosen_rarity, session)
        if not esprit_data:
            setattr(user, pity_attr, current_pity)
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
        await session.refresh(new_user_esprit)
        new_user_esprit.esprit_data = esprit_data
        return new_user_esprit, esprit_data

    async def check_rate_limit(self, interaction: discord.Interaction) -> bool:
        if not await self.rate_limiter.check(str(interaction.user.id)):
            await interaction.followup.send("You're summoning too quickly! Please wait a moment.")
            return False
        return True

    @app_commands.command(name="summon", description="Summon Esprits from the specified banner.")
    @app_commands.describe(banner="Banner to summon from.", amount="Use '10' for a multi-summon.")
    async def summon(self, interaction: discord.Interaction, banner: Literal["standard", "premium", "daily"], amount: Optional[Literal[10]] = None):
        await interaction.response.defer()
        try:
            if not await self.check_rate_limit(interaction):
                return

            if interaction.user.id in ACTIVE_SUMMON_VIEWS:
                return await interaction.followup.send("You already have a summon view open. Finish it before summoning again.")

            async with get_session() as session:
                user = await session.get(User, str(interaction.user.id))
                if not user:
                    return await interaction.followup.send("❌ You need to `/start` your journey first!")

                summon_count = 10 if amount == 10 else 1
                cost_str = "Free"

                if banner == "daily":
                    if summon_count > 1:
                        return await interaction.followup.send("❌ Only single daily summon allowed.")
                    hours_cd = self.summon_settings["cooldowns"]["daily_summon_hours"]
                    if user.last_daily_summon and datetime.utcnow() < user.last_daily_summon + timedelta(hours=hours_cd):
                        remaining = user.last_daily_summon + timedelta(hours=hours_cd) - datetime.utcnow()
                        h, rem = divmod(int(remaining.total_seconds()), 3600)
                        m, _ = divmod(rem, 60)
                        return await interaction.followup.send(f"⏳ Daily summon on cooldown. Try again in **{h}h {m}m**.")
                    user.last_daily_summon = datetime.utcnow()
                else:
                    cost_config = self.summon_settings["summoning"]["banners"][banner]
                    currency_attr = cost_config["currency"]
                    cost_per = cost_config["cost_single"]
                    total_cost = cost_config.get("cost_multi", cost_per * 10) if summon_count == 10 else cost_per
                    if getattr(user, currency_attr) < total_cost:
                        return await interaction.followup.send(f"❌ Not enough {currency_attr.replace('_', ' ').title()}. Need {total_cost}.")
                    setattr(user, currency_attr, getattr(user, currency_attr) - total_cost)
                    currency_pretty = currency_attr.replace("_", " ").title()
                    cost_str = f"{total_cost} {currency_pretty}"

                summon_results = []
                for _ in range(summon_count):
                    result = await self._internal_perform_summon(user, banner, session)
                    if result:
                        summon_results.append(result)

                if not summon_results:
                    return await interaction.followup.send("Summoning failed to find any Esprits. Please try again.")

                await session.commit()

                for user_esprit, esprit_data in summon_results:
                    log_cost = cost_str if summon_count == 1 else f"{cost_str} (x10)"
                    transaction_logger.log_summon(interaction, banner, log_cost, esprit_data, user_esprit)

                if (esprit_cog := self.bot.get_cog("EspritCog")):
                    await esprit_cog.group._invalidate(str(interaction.user.id))

                # --- Result Handling ---
                ACTIVE_SUMMON_VIEWS.add(interaction.user.id)
                if summon_count == 1:
                    user_esprit, esprit_data = summon_results[0]
                    power = user_esprit.calculate_power(
                        self.combat_settings.get("power_calculation", {}),
                        self.combat_settings.get("stat_calculation", {})
                    )
                    emoji = self.class_visuals.get(esprit_data.class_name, "❓")
                    uid = str(user_esprit.id)[:6]
                    embed = discord.Embed(
                        title=f"{interaction.user.display_name} summoned an Esprit!",
                        description=f"{emoji} **{esprit_data.class_name}**\n**{esprit_data.rarity}** | Sigil: 💥 **{power}**",
                        color=self._get_rarity_color(esprit_data.rarity)
                    )
                    embed.set_footer(text=f"UID: {uid}")
                    card_pil = await self.image_generator.render_esprit_card(esprit_data.model_dump())
                    with io.BytesIO() as buf:
                        card_pil.save(buf, "PNG")
                        file = discord.File(io.BytesIO(buf.getvalue()), filename="esprit_card.png")
                    embed.set_image(url="attachment://esprit_card.png")
                    view = EspritSummonPaginationView(
                        bot=self.bot,
                        pages=[(embed, buf.getvalue(), (user_esprit, esprit_data))],
                        author_id=interaction.user.id,
                    )
                    await interaction.followup.send(
                        embed=embed,
                        file=file,
                        view=view
                    )
                else:
                    pagination_view = await EspritSummonPaginationView.create(
                        bot=self.bot,
                        summons=summon_results,
                        class_visuals=self.class_visuals,
                        rarity_visuals=self.rarity_visuals,
                        image_generator=self.image_generator,
                        author_id=interaction.user.id
                    )
                    initial_embed, initial_image_bytes, _ = pagination_view.pages[0]
                    initial_file = discord.File(io.BytesIO(initial_image_bytes), filename="card_0.png")
                    await interaction.followup.send(
                        content=f"{interaction.user.mention} performed a x10 summon!",
                        embed=initial_embed,
                        file=initial_file,
                        view=pagination_view
                    )
        except Exception as e:
            logger.error(f"/summon error: {e}")
            logger.error(traceback.format_exc())
            if interaction.response.is_done():
                await interaction.followup.send("❌ Unexpected error occurred. Devs notified.")
            else:
                await interaction.response.send_message("❌ Unexpected error occurred. Devs notified.")
        finally:
            # Remove lockout on error or completion
            ACTIVE_SUMMON_VIEWS.discard(interaction.user.id)

async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))
    logger.info("✅ SummonCog loaded")

