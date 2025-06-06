# src/cogs/summon_cog.py

import random
import io
import discord

from discord.ext import commands
from discord import app_commands

from typing import Dict, Any, List, Tuple

from PIL import Image

import sqlalchemy as sa
from sqlalchemy.future import select
from src.database.models import User, EspritData, UserEsprit
from src.database.db import get_session

from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager
from src.utils.rng_manager import RNGManager
from src.utils.image_generator import ImageGenerator

logger = get_logger(__name__)


class SummonCog(commands.Cog):
    """
    /summon n  → Summon 1, 3 or 10 Esprits, with costs driven by game_settings.json.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = ConfigManager()

        # Load rarity weights
        raw_rarity = cfg.get_config("data/config/rarity_tiers") or {}
        self.rarity_weights: Dict[str, float] = {}
        for tier_name, tier_data in raw_rarity.items():
            prob = tier_data.get("probability")
            if isinstance(prob, (int, float)):
                self.rarity_weights[tier_name] = float(prob)
        if not self.rarity_weights:
            logger.error("SummonCog: Invalid or missing rarity_tiers config.")
        else:
            logger.info(f"SummonCog: Loaded {len(self.rarity_weights)} rarity tiers.")

        # Load rarity visuals
        self.rarity_cfg: Dict[str, Any] = cfg.get_config("data/config/rarity_visuals") or {}
        if not isinstance(self.rarity_cfg, dict):
            logger.warning("SummonCog: rarity_visuals config missing or invalid.")
            self.rarity_cfg = {}

        # Load Esprits
        raw_esprits = cfg.get_config("data/config/esprits") or {}
        self.esprits_list: List[Dict[str, Any]] = []
        for esprit_id, esprit_data in raw_esprits.items():
            entry = esprit_data.copy()
            entry["esprit_id"] = esprit_id
            if "name" in entry and "rarity" in entry and "base_hp" in entry:
                self.esprits_list.append(entry)
        if not self.esprits_list:
            logger.error("SummonCog: Invalid or missing esprits config.")
        else:
            logger.info(f"SummonCog: Loaded {len(self.esprits_list)} Esprits.")

        # RNG & image managers
        self.rng = RNGManager()
        self.image_generator = ImageGenerator()

        # --- Costs & constants (Old hardcoded values)
        # --- self.COST_SINGLE = 100
        # --- self.COST_TRIPLE = 300
        # --- self.COST_TEN    = 1000
        # +++ NEW: Load game settings to get summon costs
        self.game_settings = cfg.get_config("data/config/game_settings") or {}
        summon_config = self.game_settings.get("summon_types", {}).get("standard", {})
        
        self.COST_SINGLE = summon_config.get("cost_gold", 100)
        # Derive multi-pull costs from the single cost for consistency
        self.COST_TRIPLE = self.COST_SINGLE * 3
        self.COST_TEN = self.COST_SINGLE * 10

        # For resizing detail cards
        self.SCALE_FACTOR = 0.6


    def _get_rarity_color_hex(self, rarity: str) -> str:
        cfg_entry = self.rarity_cfg.get(rarity)
        if isinstance(cfg_entry, dict):
            return cfg_entry.get("border_color", "#FFFFFF")
        return "#FFFFFF"


    def _choose_random_esprit(self, rarity: str) -> Dict[str, Any]:
        pool = [e for e in self.esprits_list if e["rarity"] == rarity]
        return random.choice(pool) if pool else None


    class PaginatedView(discord.ui.View):
        def __init__(self, parent: "SummonCog", user_id: int,
                     pages: List[Tuple[bytes, Dict[str, Any]]]):
            super().__init__(timeout=None)
            self.parent = parent
            self.user_id = user_id
            self.pages = pages
            self.total = len(pages)
            self.current_index = 0

        def _build_embed_and_file(self) -> Tuple[discord.Embed, discord.File]:
            idx = self.current_index
            image_bytes, esprit = self.pages[idx]

            hex_color = self.parent._get_rarity_color_hex(esprit["rarity"])
            try:
                color = discord.Color(int(hex_color.lstrip("#"), 16))
            except:
                color = discord.Color.light_gray()

            sigil_val = esprit.get("sigil", None)
            sigil_icon = esprit.get("sigil_icon", "")
            if sigil_val not in (None, "", 0):
                desc = f"{sigil_icon} Sigil: **{sigil_val}**"
            else:
                desc = None

            title_text = f"✨ Summoning Result ({idx+1}/{self.total}) ✨"
            embed = discord.Embed(title=title_text, description=desc, color=color)

            filename = f"summon_{self.user_id}_{random.randint(0,9999)}.png"
            file_obj = discord.File(fp=io.BytesIO(image_bytes), filename=filename)
            embed.set_image(url=f"attachment://{filename}")
            return embed, file_obj

        @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary,
                           custom_id="prev_card")
        async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "Only the summoner can page through these cards.", ephemeral=True
                )
            self.current_index = (self.current_index - 1) % self.total
            embed, file_obj = self._build_embed_and_file()
            await interaction.response.edit_message(embed=embed, attachments=[file_obj], view=self)

        @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary,
                           custom_id="next_card")
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "Only the summoner can page through these cards.", ephemeral=True
                )
            self.current_index = (self.current_index + 1) % self.total
            embed, file_obj = self._build_embed_and_file()
            await interaction.response.edit_message(embed=embed, attachments=[file_obj], view=self)


    @app_commands.command(
        name="summon",
        description="Summon 1, 3, or 10 Esprits at once (writes into SQL)."
    )
    @app_commands.describe(amount="Must be 1, 3, or 10")
    async def summon(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(thinking=True)
        user_id = str(interaction.user.id)

        if amount not in (1, 3, 10):
            return await interaction.followup.send(
                "❌ Invalid `amount`. You may only summon 1, 3, or 10 at a time.",
                ephemeral=True
            )

        cost = (
            self.COST_SINGLE if amount == 1
            else (self.COST_TRIPLE if amount == 3 else self.COST_TEN)
        )

        async with get_session() as session:
            stmt_user = select(User).where(User.user_id == user_id)
            user_obj = (await session.execute(stmt_user)).scalar_one_or_none()

            if user_obj is None:
                return await interaction.followup.send(
                    "❌ You need to `/start` first before you can summon.", ephemeral=True
                )

            if user_obj.gold < cost:
                return await interaction.followup.send(
                    f"❌ You need **{cost} gold** to summon {amount} Esprits, but you only have **{user_obj.gold} gold**.",
                    ephemeral=True
                )

            user_obj.gold -= cost
            session.add(user_obj)
            await session.commit()

            pages: List[Tuple[bytes, Dict[str, Any]]] = []

            for _count in range(amount):
                chosen_rarity = self.rng.get_random_rarity(self.rarity_weights, luck_modifier=0.0)
                if not chosen_rarity:
                    user_obj.gold += cost
                    session.add(user_obj)
                    await session.commit()
                    return await interaction.followup.send(
                        "❌ Summon RNG failed. Your gold has been refunded.", ephemeral=True
                    )

                spirit_dict = self._choose_random_esprit(chosen_rarity)
                if not spirit_dict:
                    user_obj.gold += cost
                    session.add(user_obj)
                    await session.commit()
                    return await interaction.followup.send(
                        f"❌ No Esprits of rarity `{chosen_rarity}` found. Gold refunded.",
                        ephemeral=True
                    )

                class _TempInst:
                    current_level = 1
                    current_hp = spirit_dict.get("base_hp", 0)
                temp_inst = _TempInst()

                try:
                    card_pil: Image.Image = await self.image_generator.render_esprit_detail_image(
                        esprit_data_dict=spirit_dict,
                        esprit_instance=temp_inst
                    )
                except Exception as exc:
                    user_obj.gold += cost
                    session.add(user_obj)
                    await session.commit()
                    logger.error(f"Error rendering detail-card: {exc}", exc_info=True)
                    return await interaction.followup.send(
                        "❌ Error generating card images. Your gold has been refunded.",
                        ephemeral=True
                    )

                if not card_pil:
                    user_obj.gold += cost
                    session.add(user_obj)
                    await session.commit()
                    return await interaction.followup.send(
                        "❌ Missing sprite asset. Gold refunded.", ephemeral=True
                    )

                w, h = card_pil.size
                new_w = int(w * self.SCALE_FACTOR)
                new_h = int(h * self.SCALE_FACTOR)
                resized = card_pil.resize((new_w, new_h), Image.Resampling.NEAREST)

                with io.BytesIO() as buffer:
                    resized.save(buffer, format="PNG")
                    image_bytes = buffer.getvalue()

                new_u_e = UserEsprit(
                    owner_id=user_id,
                    esprit_data_id=spirit_dict["esprit_id"],
                    current_hp=spirit_dict.get("base_hp", 0),
                    current_level=1,
                    current_xp=0
                )
                session.add(new_u_e)
                await session.commit()

                pages.append((image_bytes, spirit_dict))

            view = SummonCog.PaginatedView(self, interaction.user.id, pages)
            embed, file_obj = view._build_embed_and_file()
            await interaction.followup.send(embed=embed, file=file_obj, view=view)


    @summon.error
    async def summon_error(self, interaction: discord.Interaction, error):
        logger.error(f"Unhandled error in /summon: {error}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(
                "An unexpected error occurred while trying to summon. Please try again later.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An unexpected error occurred. Please try again later.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SummonCog(bot))



