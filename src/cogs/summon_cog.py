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
        cfg = self.bot.config_manager
        
        self.rarity_visuals = cfg.get_config("data/config/rarity_visuals") or {}
        self.class_visuals = cfg.get_config("data/config/class_visuals") or {}
        self.rarity_tiers = cfg.get_config("data/config/rarity_tiers") or {}
        self.rarity_weights = {k: v.get("probability", 0) for k, v in self.rarity_tiers.items()}
        
        self.rng = RNGManager()
        self.image_generator = ImageGenerator(self.assets_base)

        game_settings = cfg.get_config("data/config/game_settings") or {}
        self.COST_SINGLE = game_settings.get("summon_types", {}).get("standard", {}).get("cost_nyxie", 100)
        self.COST_TEN = self.COST_SINGLE * 10

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
            super().__init__(timeout=None)
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

    @app_commands.command(name="summon", description="Summon Esprits.")
    @app_commands.describe(amount="The number of summons to perform. Must be 1 or 10.")
    async def summon(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(thinking=True)
        if amount not in (1, 10):
            return await interaction.followup.send("❌ Invalid `amount`. You may only summon 1 or 10 at a time.", ephemeral=True)
        
        cost = self.COST_SINGLE if amount == 1 else self.COST_TEN
        user_id = str(interaction.user.id)

        try:
            async with get_session() as session:
                user_obj = await session.get(User, user_id)
                if not user_obj:
                    return await interaction.followup.send("❌ You need to `/start` first.", ephemeral=True)
                if user_obj.nyxies < cost:
                    return await interaction.followup.send(f"❌ You need **{cost} nyxies** to perform this summon.", ephemeral=True)
                
                user_obj.nyxies -= cost
                session.add(user_obj)
                
                pages = []
                new_esprits_to_add = []
                loop = asyncio.get_running_loop()
                for _ in range(amount):
                    chosen_rarity = self.rng.get_random_rarity(self.rarity_weights)
                    spirit_obj = await self._choose_random_esprit(chosen_rarity, session)
                    if not spirit_obj:
                        raise ValueError(f"Failed to roll an Esprit for rarity: {chosen_rarity}")

                    spirit_dict = spirit_obj.model_dump()
                    render_func = partial(self.image_generator.render_esprit_card, esprit_data=spirit_dict)
                    card_pil = await loop.run_in_executor(None, render_func)
                    
                    with io.BytesIO() as buffer:
                        card_pil.save(buffer, format="PNG")
                        image_bytes = buffer.getvalue()
                    
                    new_u_e = UserEsprit(owner_id=user_id, esprit_data_id=spirit_obj.esprit_id, current_hp=spirit_obj.base_hp, current_level=1, current_xp=0)
                    new_esprits_to_add.append(new_u_e)
                    pages.append((image_bytes, spirit_obj))
                
                session.add_all(new_esprits_to_add)
                await session.commit()
                
                view = self.PaginatedView(self, interaction.user.id, pages)
                embed, files = view._build_embed_and_files()
                await interaction.followup.send(embed=embed, files=files, view=view)
        except Exception as e:
            logger.error(f"Error in /summon: {e}", exc_info=True)
            await interaction.followup.send("An unexpected error occurred. Your nyxies was not spent.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))
    logger.info("✅ SummonCog loaded")