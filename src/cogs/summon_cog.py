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
        
        # --- SIMPLIFIED: No more shard math needed here! ---
        # The SummonCog no longer needs to know about shard conversion.
        
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

    # --- CHANGED: This is the updated /summon command logic ---
    @app_commands.command(name="summon", description="Summon Esprits using Azurites.")
    @app_commands.describe(amount="The number of summons to perform. Must be 1 or 10.")
    async def summon(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(thinking=True)
        if amount not in (1, 10):
            return await interaction.followup.send("❌ Invalid `amount`. You may only summon 1 or 10 at a time.", ephemeral=True)
        
        # The cost is now in WHOLE Azurites, which are loaded from config.
        game_settings = self.bot.config_manager.get_config("data/config/game_settings") or {}
        banner_settings = game_settings.get("summoning", {}).get("banners", {}).get("standard", {})
        cost_in_azurites = banner_settings.get("cost_single", 1) if amount == 1 else banner_settings.get("cost_multi", 10)

        user_id = str(interaction.user.id)

        try:
            async with get_session() as session:
                user_obj = await session.get(User, user_id)
                if not user_obj:
                    return await interaction.followup.send("❌ You need to `/start` first.", ephemeral=True)
                
                # Check against the user's REAL azurites balance.
                if user_obj.azurites < cost_in_azurites:
                    return await interaction.followup.send(
                        f"❌ You don't have enough Azurites. You need **{cost_in_azurites}** but you only have **{user_obj.azurites}**.\n"
                        f"Use `/craft azurite` to convert your shards!", 
                        ephemeral=True
                    )
                
                # Subtract the cost from the azurites balance.
                user_obj.azurites -= cost_in_azurites
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
                    user_obj.azurites += cost_in_azurites # Refund the user
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