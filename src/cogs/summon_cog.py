# src/cogs/summon_cog.py

import random
import io
import discord

from discord.ext import commands
from discord import app_commands
from typing import Dict, Any, List, Optional, Tuple

from PIL import Image

from ..utils.logger import get_logger
from ..utils.config_manager import ConfigManager
from ..utils.rng_manager import RNGManager
from ..utils.image_generator import ImageGenerator
from ..utils.economy_manager import EconomyManager
from ..utils.inventory_manager import InventoryManager

logger = get_logger(__name__)


class SummonCog(commands.Cog):
    """
    This single Cog now contains:
      • /start       → register (500 gold + 1 Epic Esprit)
      • /balance     → show gold & dust
      • /inventory   → list owned Esprits
      • /daily       → claim 100 gold once per 24h
      • /summon n    → paginated detail‐cards (amount ∈ {1,3,10})

    We keep everything here so you don’t have to jump between files.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = ConfigManager()

        # ── Load rarity weights ──────────────────────────────────
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

        # ── Load rarity visuals (to pick border_color later) ─────
        self.rarity_cfg: Dict[str, Any] = cfg.get_config("data/config/rarity_visuals") or {}
        if not isinstance(self.rarity_cfg, dict):
            logger.warning("SummonCog: rarity_visuals config missing or invalid.")
            self.rarity_cfg = {}

        # ── Load Esprits ────────────────────────────────────────
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

        # RNG, image, economy, inventory managers
        self.rng = RNGManager()
        self.image_generator = ImageGenerator()
        self.economy = EconomyManager("data/economy.json")
        self.inventory = InventoryManager("data/inventory.json")

        # Costs & constants
        self.START_AMOUNT = 500
        self.COST_SINGLE = 100
        self.COST_TRIPLE = 300
        self.COST_TEN    = 1000
        self.DAILY_AMOUNT = 100

        # When resizing each detail‐card so it’s still legible on mobile:
        self.SCALE_FACTOR = 0.6

    # ────────────────────────────────────────────────────────────────────────────
    #    SHARED HELPERS
    # ────────────────────────────────────────────────────────────────────────────

    def _get_rarity_color_hex(self, rarity: str) -> str:
        cfg_entry = self.rarity_cfg.get(rarity)
        if isinstance(cfg_entry, dict):
            return cfg_entry.get("border_color", "#FFFFFF")
        return "#FFFFFF"

    def _choose_random_esprit(self, rarity: str) -> Optional[Dict[str, Any]]:
        pool = [e for e in self.esprits_list if e.get("rarity") == rarity]
        return random.choice(pool) if pool else None

    # ────────────────────────────────────────────────────────────────────────────
    #    /start COMMAND
    # ────────────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="start",
        description="Register your account: +500 gold and a random Epic Esprit."
    )
    async def start(self, interaction: discord.Interaction):
        """
        If the user already has any gold or any inventory, we tell them they’ve already started.
        Otherwise, give 500 gold + a random Epic Esprit into their inventory.
        """
        user_id = interaction.user.id
        bal = self.economy.get_balance(user_id)
        inv = self.inventory.get_inventory(user_id)

        if bal > 0 or inv:
            embed = discord.Embed(
                title="🔄 Already Started",
                description=(
                    f"You already have **{bal} gold** and **{len(inv)} Esprits**.\n"
                    "Use /balance, /inventory, or /summon to continue."
                ),
                color=discord.Color.light_grey()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Grant 500 gold
        self.economy.add_balance(user_id, self.START_AMOUNT)

        # Grant a random Epic Esprit
        epic = self._choose_random_esprit("Epic")
        if epic:
            self.inventory.add_esprit(user_id, epic["esprit_id"])
            esprit_name = epic["name"]
        else:
            esprit_name = "None (config error)"

        new_bal = self.economy.get_balance(user_id)
        embed = discord.Embed(
            title="🚀 Account Started",
            description=(
                f"You received **{self.START_AMOUNT} gold** and "
                f"**1 Epic Esprit ({esprit_name})**!\n"
                f"Your balance is now **{new_bal} gold**."
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @start.error
    async def start_error(self, interaction: discord.Interaction, error):
        logger.error(f"Error in /start: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Unexpected error. Please try again later.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Unexpected error. Please try again later.", ephemeral=True
            )

    # ────────────────────────────────────────────────────────────────────────────
    #    /balance COMMAND
    # ────────────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="balance",
        description="Check your current gold and dust."
    )
    async def balance(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        bal = self.economy.get_balance(user_id)
        dust = self.economy.get_dust(user_id)
        embed = discord.Embed(
            title="💰 Your Wallet",
            description=f"You have **{bal} gold** and **{dust} dust**.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @balance.error
    async def balance_error(self, interaction: discord.Interaction, error):
        logger.error(f"Error in /balance: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Unexpected error. Please try again later.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Unexpected error. Please try again later.", ephemeral=True
            )

    # ────────────────────────────────────────────────────────────────────────────
    #    /inventory COMMAND
    # ────────────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="inventory",
        description="View your owned Esprits."
    )
    async def inventory_cmd(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        inv_ids = self.inventory.get_inventory(user_id)
        if not inv_ids:
            embed = discord.Embed(
                title="📦 Your Inventory",
                description="You don’t own any Esprits yet.",
                color=discord.Color.light_grey()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Build a list of names from config
        names = []
        for eid in inv_ids:
            obj = next((e for e in self.esprits_list if e["esprit_id"] == eid), None)
            names.append(obj["name"] if obj else f"(unknown: {eid})")

        desc = "\n".join(f"- {n}" for n in names)
        embed = discord.Embed(
            title="📦 Your Inventory",
            description=desc,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @inventory_cmd.error
    async def inventory_error(self, interaction: discord.Interaction, error):
        logger.error(f"Error in /inventory: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Unexpected error. Please try again later.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Unexpected error. Please try again later.", ephemeral=True
            )

    # ────────────────────────────────────────────────────────────────────────────
    #    /daily COMMAND
    # ────────────────────────────────────────────────────────────────────────────
    @app_commands.command(
        name="daily",
        description="Claim your daily 100 gold reward."
    )
    async def daily(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if self.economy.can_claim_daily(user_id):
            self.economy.claim_daily(user_id, self.DAILY_AMOUNT)
            new_bal = self.economy.get_balance(user_id)
            embed = discord.Embed(
                title="☀️ Daily Claimed",
                description=(
                    f"You received **{self.DAILY_AMOUNT} gold**!\n"
                    f"Your new balance is **{new_bal} gold**."
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            remaining = self.economy.get_time_until_next_daily(user_id)
            hrs, rem = divmod(int(remaining.total_seconds()), 3600)
            mins, secs = divmod(rem, 60)
            embed = discord.Embed(
                title="⏳ Already Claimed",
                description=(f"You can claim your next daily reward in "
                             f"**{hrs}h {mins}m {secs}s**."),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @daily.error
    async def daily_error(self, interaction: discord.Interaction, error):
        logger.error(f"Error in /daily: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Unexpected error. Please try again later.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Unexpected error. Please try again later.", ephemeral=True
            )

    # ────────────────────────────────────────────────────────────────────────────
    #    PAGINATED /summon COMMAND
    # ────────────────────────────────────────────────────────────────────────────
    class PaginatedView(discord.ui.View):
        """
        A View that holds a list of (image_bytes: bytes, esprit_data_dict) pairs.
        It lets the summoner page through with ◀️ / ▶️. Each page rebuilds
        the embed to match that card’s rarity color + sigil.
        """
        def __init__(self,
                     parent: "SummonCog",
                     user_id: int,
                     pages: List[Tuple[bytes, Dict[str, Any]]]):
            super().__init__(timeout=None)
            self.parent = parent
            self.user_id = user_id
            self.pages = pages
            self.total = len(pages)
            self.current_index = 0  # Start on page 0

        def _build_embed_and_file(self) -> Tuple[discord.Embed, discord.File]:
            """
            Build an embed and a fresh discord.File for the CURRENT page index:
            - Title shows “Page X/Y”
            - Color is the rarity color of that page’s Esprit
            - Description shows “Sigil: <value>” if applicable
            """
            idx = self.current_index
            image_bytes, esprit = self.pages[idx]

            # Determine embed color from rarity:
            hex_color = self.parent._get_rarity_color_hex(esprit.get("rarity", "Common"))
            try:
                color = discord.Color(int(hex_color.lstrip("#"), 16))
            except:
                color = discord.Color.light_gray()

            # Build description (sigil line):
            sigil_val = esprit.get("sigil", None)
            sigil_icon = esprit.get("sigil_icon", "")
            if sigil_val not in (None, "", 0):
                desc = f"{sigil_icon} Sigil: **{sigil_val}**"
            else:
                desc = None

            # Embed text:
            title_text = f"✨ Summoning Result ({idx+1}/{self.total}) ✨"
            embed = discord.Embed(title=title_text, description=desc, color=color)

            # Create a new discord.File each time from bytes:
            filename = f"summon_{self.user_id}_{random.randint(0,9999)}.png"
            file_obj = discord.File(fp=io.BytesIO(image_bytes), filename=filename)
            embed.set_image(url=f"attachment://{filename}")
            return embed, file_obj

        @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, custom_id="prev_card")
        async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "Only the summoner can page through these cards.", ephemeral=True
                )

            # Step back (wrap around):
            self.current_index = (self.current_index - 1) % self.total
            embed, file_obj = self._build_embed_and_file()

            await interaction.response.edit_message(
                embed=embed,
                attachments=[file_obj],
                view=self
            )

        @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary, custom_id="next_card")
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "Only the summoner can page through these cards.", ephemeral=True
                )

            # Step forward (wrap around):
            self.current_index = (self.current_index + 1) % self.total
            embed, file_obj = self._build_embed_and_file()

            await interaction.response.edit_message(
                embed=embed,
                attachments=[file_obj],
                view=self
            )

    @app_commands.command(
        name="summon",
        description="Summon 1, 3, or 10 Esprits at once (with pagination!)."
    )
    @app_commands.describe(amount="Must be 1, 3, or 10")
    async def summon(self, interaction: discord.Interaction, amount: int):
        """
        If amount==1, cost=100g; amount==3, cost=300g; amount==10, cost=1000g.
        Rolls that many Esprits, renders each detail‐card PIL, resizes it to ~60%
        so mobile can read it, then sends page 1 of N with ◀️▶️ buttons.
        """
        await interaction.response.defer(ephemeral=False)
        user_id = interaction.user.id

        # 1) Validate: must be 1, 3, or 10
        if amount not in (1, 3, 10):
            return await interaction.followup.send(
                "❌ Invalid `amount`. You may only summon 1, 3, or 10 at a time.", ephemeral=True
            )

        # 2) Determine cost and try to deduct
        cost = (
            self.COST_SINGLE if amount == 1
            else (self.COST_TRIPLE if amount == 3 else self.COST_TEN)
        )
        if not self.economy.deduct_balance(user_id, cost):
            bal = self.economy.get_balance(user_id)
            return await interaction.followup.send(
                f"❌ You need **{cost} gold** to summon {amount} Esprits, but you only have **{bal} gold**.",
                ephemeral=True
            )

        # 3) Roll that many Esprits, render PIL cards, resize, convert to bytes
        pages: List[Tuple[bytes, Dict[str, Any]]] = []

        for _ in range(amount):
            chosen_rarity = self.rng.get_random_rarity(self.rarity_weights, luck_modifier=0.0)
            if not chosen_rarity:
                # Refund and abort if RNG fails
                self.economy.add_balance(user_id, cost)
                return await interaction.followup.send(
                    "❌ Summon RNG failed. Your gold has been refunded.", ephemeral=True
                )

            spirit = self._choose_random_esprit(chosen_rarity)
            if not spirit:
                self.economy.add_balance(user_id, cost)
                return await interaction.followup.send(
                    f"❌ No Esprits of rarity `{chosen_rarity}` found. Gold refunded.", ephemeral=True
                )

            # Build a minimal "instance" for stats:
            class _TempInst:
                current_level = 1
                current_hp = spirit.get("base_hp", 0)

            temp_inst = _TempInst()

            try:
                card_pil: Image.Image = await self.image_generator.render_esprit_detail_image(
                    esprit_data_dict=spirit,
                    esprit_instance=temp_inst
                )
            except Exception as exc:
                # Refund on any rendering error
                self.economy.add_balance(user_id, cost)
                logger.error(f"Error rendering detail-card: {exc}", exc_info=True)
                return await interaction.followup.send(
                    "❌ Error generating card images. Your gold has been refunded.", ephemeral=True
                )

            if not card_pil:
                self.economy.add_balance(user_id, cost)
                return await interaction.followup.send(
                    "❌ Missing sprite asset. Gold refunded.", ephemeral=True
                )

            # Resize so each card stays legible on mobile
            w, h = card_pil.size
            new_w = int(w * self.SCALE_FACTOR)
            new_h = int(h * self.SCALE_FACTOR)
            resized = card_pil.resize((new_w, new_h), Image.Resampling.NEAREST)

            # Convert to PNG bytes
            with io.BytesIO() as buffer:
                resized.save(buffer, format="PNG")
                image_bytes = buffer.getvalue()

            # Immediately add to inventory
            self.inventory.add_esprit(user_id, spirit["esprit_id"])

            # Keep (bytes, spirit_dict) for pagination
            pages.append((image_bytes, spirit))

        # 4) Now that we have all `pages`, build a PaginatedView
        view = SummonCog.PaginatedView(self, user_id, pages)

        # 5) Build the page-0 embed and send it with its file
        embed, file_obj = view._build_embed_and_file()
        await interaction.followup.send(
            embed=embed,
            file=file_obj,
            view=view
        )

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


