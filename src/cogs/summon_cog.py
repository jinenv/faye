# src/cogs/summon_cog.py
import random, io, discord, asyncio
from functools import partial
from discord.ext import commands
from discord import app_commands
from typing import Dict, Any, List, Tuple
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, EspritData, UserEsprit
from src.database.db import get_session
from src.utils.image_generator import ImageGenerator
from src.utils.rng_manager import RNGManager
from src.utils.logger import get_logger

logger = get_logger(__name__)

class SummonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.assets_base = "assets"
        
        # --- Load All Required Configs ---
        cfg = self.bot.config_manager
        self.rarity_visuals = cfg.get_config("data/config/rarity_visuals") or {}
        self.class_visuals = cfg.get_config("data/config/class_visuals") or {}
        
        game_settings = cfg.get_config("data/config/game_settings") or {}
        summoning_settings = game_settings.get("summoning", {}).get("banners", {}).get("standard", {})
        
        # --- Implement Azurite Conversion Logic ---
        # The cost in the config is in WHOLE Azurites.
        # We define the conversion rate here. This could also be in the config.
        self.SHARDS_PER_AZURITE = 10 
        
        # Calculate the actual cost in SHARDS.
        cost_single_azurites = summoning_settings.get("cost_single", 1)
        cost_multi_azurites = summoning_settings.get("cost_multi", 10)
        
        self.COST_SINGLE_SHARDS = cost_single_azurites * self.SHARDS_PER_AZURITE
        self.COST_MULTI_SHARDS = cost_multi_azurites * self.SHARDS_PER_AZURITE
        
        # Load rarity probabilities
        self.rarity_weights = summoning_settings.get("rarity_distribution", {})

        self.rng = RNGManager()
        self.image_generator = ImageGenerator(self.assets_base)

    def _get_rarity_color(self, rarity_name: str) -> discord.Color:
        hex_color = (self.rarity_visuals.get(rarity_name) or {}).get("border_color", "#FFFFFF")
        return discord.Color(int(hex_color.lstrip("#"), 16))

    async def _choose_random_esprit(self, rarity: str, session: AsyncSession) -> EspritData | None:
        stmt = select(EspritData).where(EspritData.rarity == rarity)
        result = await session.execute(stmt)
        pool = result.scalars().all()
        return random.choice(pool) if pool else None

    class PaginatedView(discord.ui.View):
        # This sub-class is well-designed and does not need changes.
        def __init__(self, parent_cog: "SummonCog", user_id: int, pages: List[Tuple[bytes, EspritData]]):
            super().__init__(timeout=300)
            self.parent_cog = parent_cog
            self.user_id = user_id
            self.pages = pages
            self.total = len(pages)
            self.current_index = 0

        def _build_embed_and_files(self) -> Tuple[discord.Embed, List[discord.File]]:
            idx = self.current_index
            image_bytes, esprit_data = self.pages[idx]
            rarity_name = esprit_data.rarity
            color = self.parent_cog._get_rarity_color(rarity_name)
            title = f"✨ Summoning Result ({idx + 1}/{self.total}) ✨"
            class_name = esprit_data.class_name
            class_emoji = self.parent_cog.class_visuals.get(class_name, "❓")
            description = f"{class_emoji} {class_name} | **{rarity_name}**"
            embed = discord.Embed(title=title, description=description, color=color)
            files_to_send = [discord.File(fp=io.BytesIO(image_bytes), filename="esprit_card.png")]
            embed.set_image(url=f"attachment://{files_to_send[0].filename}")
            return embed, files_to_send
        
        async def _update_view(self, interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("Only the summoner can page through these cards.", ephemeral=True)
            embed, files = self._build_embed_and_files()
            await interaction.response.edit_message(embed=embed, attachments=files, view=self)

        @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
        async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.current_index = (self.current_index - 1) % self.total
            await self._update_view(interaction)

        @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.current_index = (self.current_index + 1) % self.total
            await self._update_view(interaction)

    @app_commands.command(name="summon", description="Summon Esprits using Azurites.")
    @app_commands.describe(amount="The number of summons to perform. Must be 1 or 10.")
    async def summon(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(thinking=True)
        if amount not in (1, 10):
            return await interaction.followup.send("❌ Invalid `amount`. You may only summon 1 or 10 at a time.", ephemeral=True)
        
        # Determine the cost in SHARDS based on the summon amount.
        cost_in_shards = self.COST_SINGLE_SHARDS if amount == 1 else self.COST_MULTI_SHARDS
        user_id = str(interaction.user.id)

        try:
            async with get_session() as session:
                user_obj = await session.get(User, user_id)
                if not user_obj:
                    return await interaction.followup.send("❌ You need to `/start` first.", ephemeral=True)
                
                # Check against the user's azurite_shards balance.
                if user_obj.azurite_shards < cost_in_shards:
                    needed_azurites = cost_in_shards / self.SHARDS_PER_AZURITE
                    return await interaction.followup.send(f"❌ You need **{needed_azurites:.0f} Azurites** ({cost_in_shards} Shards) for this summon.", ephemeral=True)
                
                # Subtract the cost from the azurite_shards balance.
                user_obj.azurite_shards -= cost_in_shards
                session.add(user_obj)
                
                pages = []
                new_esprits_to_add = []
                loop = asyncio.get_running_loop()

                for _ in range(amount):
                    chosen_rarity = self.rng.get_random_rarity(self.rarity_weights)
                    spirit_obj = await self._choose_random_esprit(chosen_rarity, session)
                    if not spirit_obj:
                        logger.warning(f"Failed to find an Esprit for rarity '{chosen_rarity}'. Skipping one summon.")
                        continue

                    spirit_dict = spirit_obj.model_dump()
                    render_func = partial(self.image_generator.render_esprit_card, esprit_data=spirit_dict)
                    card_pil = await loop.run_in_executor(None, render_func)
                    
                    with io.BytesIO() as buffer:
                        card_pil.save(buffer, format="PNG")
                        image_bytes = buffer.getvalue()
                    
                    new_u_e = UserEsprit(owner_id=user_id, esprit_data_id=spirit_obj.esprit_id, current_hp=spirit_obj.base_hp, current_level=1, current_xp=0)
                    new_esprits_to_add.append(new_u_e)
                    pages.append((image_bytes, spirit_obj))
                
                if not pages:
                    # This happens if all esprit lookups failed.
                    user_obj.azurite_shards += cost_in_shards # Refund the user
                    session.add(user_obj)
                    await session.commit()
                    return await interaction.followup.send("An error occurred while finding Esprits to summon. Your Azurites were not spent.", ephemeral=True)

                session.add_all(new_esprits_to_add)
                await session.commit()
                
                view = self.PaginatedView(self, interaction.user.id, pages)
                embed, files = view._build_embed_and_files()
                await interaction.followup.send(embed=embed, files=files, view=view)

        except Exception as e:
            logger.error(f"Error in /summon: {e}", exc_info=True)
            await interaction.followup.send("An unexpected error occurred. Please contact support if the issue persists.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))
    logger.info("✅ SummonCog loaded")