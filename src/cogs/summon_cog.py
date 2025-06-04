# src/cogs/summon_cog.py

import random
import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, Any, Optional

from ..utils.logger import get_logger
from ..utils.config_manager import ConfigManager
from ..utils.rng_manager import RNGManager
from ..utils.image_generator import ImageGenerator
from ..utils.economy_manager import EconomyManager
from ..utils.inventory_manager import InventoryManager
from ..utils.render_helpers import render_pil_to_discord_file

logger = get_logger(__name__)


class SummonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = ConfigManager()

        # ─── Load rarity weights ──────────────────────────
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

        # ─── Load rarity visuals (for colors) ────────────
        self.rarity_cfg = cfg.get_config("data/config/rarity_visuals") or {}
        if not isinstance(self.rarity_cfg, dict):
            logger.warning("SummonCog: rarity_visuals config missing or invalid.")
            self.rarity_cfg = {}

        # ─── Load Esprits ──────────────────────────────────
        raw_esprits = cfg.get_config("data/config/esprits") or {}
        self.esprits_list: list[Dict[str, Any]] = []
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

        # Constants
        self.DAILY_AMOUNT = 100    # gold from /daily
        self.SUMMON_COST   = 100   # gold per /summon
        self.START_AMOUNT  = 500   # gold + Epic Esprit from /start

        # Dust ranges by rarity
        self.DUST_RANGES = {
            "Common":      (1, 10),
            "Uncommon":    (10, 25),
            "Rare":        (25, 50),
            "Epic":        (50, 100),
            "Legendary":   (100, 200),
            "Mythic":      (200, 500),
            # If you have a “Supreme” tier, just add it here:
            # "Supreme":   (500, 1000),
        }

    def _get_rarity_color_hex(self, rarity: str) -> str:
        cfg_entry = self.rarity_cfg.get(rarity)
        if isinstance(cfg_entry, dict):
            return cfg_entry.get("border_color", "#FFFFFF")
        return "#FFFFFF"

    def _choose_random_esprit(self, rarity: str) -> Optional[Dict[str, Any]]:
        candidates = [e for e in self.esprits_list if e.get("rarity") == rarity]
        return random.choice(candidates) if candidates else None

    def _choose_random_by_tier(self, tier: str) -> Optional[Dict[str, Any]]:
        return self._choose_random_esprit(tier)

    class _SummonView(discord.ui.View):
        """
        A Discord UI View with three buttons: [Claim] [Discard] [Info].
        - Claim: adds the Esprit to inventory.
        - Discard: awards dust based on rarity‐specific random range.
        - Info: shows ephemeral details.
        """
        def __init__(
            self,
            parent: "SummonCog",
            summoned: Dict[str, Any],
            temp_instance: Any,
            author_id: int
        ):
            super().__init__(timeout=None)
            self.parent = parent
            self.summoned = summoned
            self.temp_instance = temp_instance
            self.author_id = author_id
            self.esprit_id = summoned.get("esprit_id")

        async def _disable_buttons(self, interaction: discord.Interaction):
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)

        @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="claim_button")
        async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message(
                    "Only the summoner may claim this Esprit.", ephemeral=True
                )

            # Add to inventory
            self.parent.inventory.add_esprit(self.author_id, self.esprit_id)
            await self._disable_buttons(interaction)
            await interaction.followup.send(
                f"✅ You claimed **{self.summoned.get('name')}** into your inventory!",
                ephemeral=True
            )

        @discord.ui.button(label="Discard", style=discord.ButtonStyle.danger, custom_id="discard_button")
        async def discard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message(
                    "Only the summoner may discard this Esprit.", ephemeral=True
                )

            rarity = self.summoned.get("rarity", "Common")
            # Look up the correct range; if not found, default to (1, 10)
            rmin, rmax = self.parent.DUST_RANGES.get(rarity, (1, 10))
            dust_awarded = random.randint(rmin, rmax)

            self.parent.economy.add_dust(self.author_id, dust_awarded)
            await self._disable_buttons(interaction)
            await interaction.followup.send(
                f"🗑️ You discarded **{self.summoned.get('name')}** "
                f"and received **{dust_awarded} dust**.",
                ephemeral=True
            )

        @discord.ui.button(label="Info", style=discord.ButtonStyle.primary, custom_id="info_button")
        async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message(
                    "Only the summoner may view this info.", ephemeral=True
                )

            # Show a detailed ephemeral embed
            e = discord.Embed(
                title=f"{self.summoned.get('name', 'Unknown')} — Details",
                color=discord.Color.blue()
            )
            si = self.summoned
            ti = self.temp_instance
            description = (
                f"**Rarity:** {si.get('rarity')}\n"
                f"**Level:** {ti.current_level}\n"
                f"**HP:** {ti.current_hp}\n"
                f"**ATK:** {si.get('base_attack', 0)}\n"
                f"**DEF:** {si.get('base_defense', 0)}\n"
                f"**SPD:** {si.get('base_speed', 0)}\n"
                f"**MP:** {si.get('base_mana', 0)}\n"
                f"**MR:** {si.get('base_magic_resist', 0)}\n"
                f"**CRIT:** {si.get('base_crit_rate', 0)*100:.1f}%\n"
                f"**BLOCK:** {si.get('base_block_rate', 0)*100:.1f}%\n"
                f"**DODGE:** {si.get('base_dodge_chance', 0)*100:.1f}%\n"
                f"**MP REG:** {si.get('base_mana_regen', 0)}\n\n"
                f"**Description:** {si.get('description', 'No description.')}"
            )
            e.description = description
            await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(
        name="start",
        description="Register your account: +500 gold and a random Epic Esprit."
    )
    async def start(self, interaction: discord.Interaction):
        """
        1) If user already has any gold or inventory, say “already started.”
        2) Otherwise, give 500 gold + random Epic Esprit into inventory.
        """
        user_id = interaction.user.id
        bal = self.economy.get_balance(user_id)
        inv = self.inventory.get_inventory(user_id)

        if bal > 0 or inv:
            embed = discord.Embed(
                title="🔄 Already Started",
                description=(
                    f"You already have **{bal} gold** and "
                    f"**{len(inv)}** Esprits in inventory.\n"
                    "Use /balance, /inventory, or /summon to continue."
                ),
                color=discord.Color.light_grey()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Grant 500 gold
        self.economy.add_balance(user_id, self.START_AMOUNT)

        # Grant a random Epic Esprit
        epic_esprit = self._choose_random_by_tier("Epic")
        if epic_esprit:
            self.inventory.add_esprit(user_id, epic_esprit["esprit_id"])
            esprit_name = epic_esprit["name"]
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

    @app_commands.command(name="balance", description="Check your current gold and dust.")
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

    @app_commands.command(name="inventory", description="View your owned Esprits.")
    async def inventory(self, interaction: discord.Interaction):
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
                description=(
                    f"You can claim your next daily reward in "
                    f"**{hrs}h {mins}m {secs}s**."
                ),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="summon",
        description="Summon a random Esprit (costs 100 gold)."
    )
    async def summon(self, interaction: discord.Interaction):
        """
        1) Check if user has ≥100 gold. If not, error.
        2) Deduct 100 gold.
        3) Pick a rarity by weights → random Esprit.
        4) Build detail‐card image via PIL.
        5) Send embed with:
           • Title: “✨ Summoning Result ✨”
           • Description: “🔱 Sigil: <combat_power>” (if defined)
           • The generated PNG as embed image
           • Footer: “🔁 X duplicates • 🎟️ Y pulls left”
           • Three buttons: [Claim] [Discard] [Info]
        """
        await interaction.response.defer(ephemeral=False)
        user_id = interaction.user.id

        # 1) Check gold balance
        if not self.economy.deduct_balance(user_id, self.SUMMON_COST):
            bal = self.economy.get_balance(user_id)
            embed = discord.Embed(
                title="❌ Not Enough Gold",
                description=(
                    f"Summoning costs **{self.SUMMON_COST} gold**, "
                    f"but you only have **{bal} gold**."
                ),
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # 2) Pick a rarity
        chosen_rarity = self.rng.get_random_rarity(
            self.rarity_weights, luck_modifier=0.0
        )
        if not chosen_rarity:
            self.economy.add_balance(user_id, self.SUMMON_COST)
            await interaction.followup.send(
                "❌ Failed to determine rarity. Your gold has been refunded.",
                ephemeral=True
            )
            logger.error("RNGManager.get_random_rarity returned None.")
            return

        # 3) Choose a random Esprit of that rarity
        summoned = self._choose_random_esprit(chosen_rarity)
        if not summoned:
            self.economy.add_balance(user_id, self.SUMMON_COST)
            await interaction.followup.send(
                f"❌ No Esprits found for rarity '{chosen_rarity}'. Your gold has been refunded.",
                ephemeral=True
            )
            logger.warning(f"No Esprits in config have rarity '{chosen_rarity}'.")
            return

        esprit_name   = summoned.get("name", "Unknown Esprit")
        esprit_rarity = summoned.get("rarity", "Common")
        esprit_sigil_value = summoned.get("sigil", None)
        esprit_sigil_icon  = summoned.get("sigil_icon", "🔱")
        esprit_id = summoned.get("esprit_id")

        logger.info(f"Player {interaction.user} summoned {esprit_name} (rarity {esprit_rarity}).")

        # ─── Build a minimal “instance” for stats ──────────
        class _TempInstance:
            current_level = 1
            current_hp    = summoned.get("base_hp", 0)

        temp_instance = _TempInstance()

        # 4) Generate the detail‐card image
        summon_image_file = None
        try:
            summon_image_pil = await self.image_generator.render_esprit_detail_image(
                esprit_data_dict=summoned,
                esprit_instance=temp_instance
            )
            if summon_image_pil is not None:
                summon_image_file = render_pil_to_discord_file(
                    summon_image_pil, filename="summon_result.png"
                )
                logger.info("SummonCog: detail-card image generated successfully.")
            else:
                logger.info("SummonCog: sprite file missing; skipping image.")
        except Exception as e_img:
            self.economy.add_balance(user_id, self.SUMMON_COST)
            logger.error(f"SummonCog: Error generating detail-card image: {e_img}", exc_info=True)
            await interaction.followup.send(
                "❌ Error generating card image. Your gold has been refunded.",
                ephemeral=True
            )
            return

        # 5) Build the embed
        rarity_color_hex = self._get_rarity_color_hex(esprit_rarity)
        try:
            embed_color = discord.Color(int(rarity_color_hex.lstrip("#"), 16))
        except:
            embed_color = discord.Color.light_grey()

        if esprit_sigil_value not in (None, "", 0):
            desc_text = f"{esprit_sigil_icon} Sigil: {esprit_sigil_value}"
        else:
            desc_text = None

        embed = discord.Embed(
            title="✨ Summoning Result ✨",
            description=desc_text,
            color=embed_color
        )

        if summon_image_file:
            embed.set_image(url="attachment://summon_result.png")

        duplicate_count = 0  # TODO: replace with actual duplicate logic
        pulls_left      = 0  # TODO: track pulls left
        footer_text = f"🔁 {duplicate_count} duplicates • 🎟️ {pulls_left} pulls left"
        embed.set_footer(text=footer_text)

        # Create the view with three buttons
        view = SummonCog._SummonView(self, summoned, temp_instance, user_id)

        if summon_image_file:
            await interaction.followup.send(embed=embed, file=summon_image_file, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

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




