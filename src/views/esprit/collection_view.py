# src/views/esprit/collection_view.py
from typing import List, Optional
from enum import Enum
import discord
from discord.ext import commands
from src.database.models import UserEsprit

MAX_PAGE_SIZE = 10
TIMEOUT = 300

class SortMethod(str, Enum):
    RARITY = "rarity"
    POWER = "power"
    LEVEL = "level"
    NAME = "name"

class EnhancedCollectionView(discord.ui.View):
    """
    A complex, paginated, filterable, and sortable view for the Esprit collection.
    REVISED: Corrected TypeError and improved readability.
    """
    def __init__(self, bot: commands.Bot, esprits: List[UserEsprit], author_id: int):
        super().__init__(timeout=TIMEOUT)
        self.bot = bot
        self.author_id = author_id
        self.all_esprits = esprits
        self.filtered_esprits = esprits[:]
        self.page = 0
        self.sort_by: SortMethod = SortMethod.RARITY
        self.rarity_filter: Optional[str] = None
        self._setup_components()

    def _get_rarity_emoji(self, rarity: str) -> str:
        # Using full rarity names for clarity
        return {
            "Common": "⚪", "Uncommon": "🟢", "Rare": "🔵", "Epic": "🟣",
            "Celestial": "🟡", "Supreme": "🔴", "Deity": "🌟"
        }.get(rarity, "❓")

    def _setup_components(self):
        # --- BUTTONS ---
        self.add_item(discord.ui.Button(label="⏮️", style=discord.ButtonStyle.secondary, row=2, custom_id="first"))
        self.add_item(discord.ui.Button(label="◀️", style=discord.ButtonStyle.secondary, row=2, custom_id="prev"))
        self.add_item(discord.ui.Button(label="▶️", style=discord.ButtonStyle.secondary, row=2, custom_id="next"))
        self.add_item(discord.ui.Button(label="⏭️", style=discord.ButtonStyle.secondary, row=2, custom_id="last"))

        # --- SORTING SELECT MENU (FIXED) ---
        sort_options = [
            discord.SelectOption(label="Rarity", value=SortMethod.RARITY.value, emoji="💎"),
            discord.SelectOption(label="Power", value=SortMethod.POWER.value, emoji="💥"),
            discord.SelectOption(label="Level", value=SortMethod.LEVEL.value, emoji="📈"),
            discord.SelectOption(label="Name", value=SortMethod.NAME.value, emoji="📝"),
        ]
        self.add_item(discord.ui.Select(placeholder="Sort by…", row=0, custom_id="sort", options=sort_options))

        # --- FILTERING SELECT MENU ---
        rarities = ["Common", "Uncommon", "Rare", "Epic", "Celestial", "Supreme", "Deity"]
        filter_options = [discord.SelectOption(label="All Rarities", value="all", emoji="🌟")] + \
                         [discord.SelectOption(label=r, value=r, emoji=self._get_rarity_emoji(r)) for r in rarities]
        self.add_item(discord.ui.Select(placeholder="Filter rarity…", row=1, custom_id="filter", options=filter_options))

    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("This is not for you.", ephemeral=True)
            return False
        
        custom_id = inter.data.get("custom_id")
        values = inter.data.get("values", [])

        if custom_id == "first": self.page = 0
        elif custom_id == "prev": self.page = max(0, self.page - 1)
        elif custom_id == "next":
            total_pages = max(1, (len(self.filtered_esprits) + MAX_PAGE_SIZE - 1) // MAX_PAGE_SIZE)
            self.page = min(total_pages - 1, self.page + 1)
        elif custom_id == "last":
            self.page = (len(self.filtered_esprits) + MAX_PAGE_SIZE - 1) // MAX_PAGE_SIZE
        elif custom_id == "sort":
            self.sort_by = SortMethod(values[0])
            self._apply_filters_and_sort()
        elif custom_id == "filter":
            self.rarity_filter = None if values[0] == "all" else values[0]
            self._apply_filters_and_sort()
        
        await self.update_message(inter)
        return True
    
    def _apply_filters_and_sort(self):
        # Apply filtering
        self.filtered_esprits = [e for e in self.all_esprits if not self.rarity_filter or e.esprit_data.rarity == self.rarity_filter]
        
        # Get configs with readable variable names
        combat_cfg = self.bot.config.get("combat_settings", {})
        power_cfg = combat_cfg.get("power_calculation", {})
        stat_cfg = combat_cfg.get("stat_calculation", {})
        
        # A robust, readable rarity sorting map
        rarity_order = {rarity: i for i, rarity in enumerate(["Deity", "Supreme", "Celestial", "Epic", "Rare", "Uncommon", "Common"])}

        # Apply sorting
        self.filtered_esprits.sort(
            key=lambda e: (
                e.esprit_data.name if self.sort_by == SortMethod.NAME else
                e.current_level if self.sort_by == SortMethod.LEVEL else
                e.calculate_power(power_cfg, stat_cfg) if self.sort_by == SortMethod.POWER else
                rarity_order.get(e.esprit_data.rarity, 99) # Default to last for unknown rarities
            ),
            reverse=(self.sort_by in [SortMethod.LEVEL, SortMethod.POWER])
        )
        self.page = 0

    def _get_page_embed(self) -> discord.Embed:
        total_filtered = len(self.filtered_esprits)
        total_pages = max(1, (total_filtered + MAX_PAGE_SIZE - 1) // MAX_PAGE_SIZE)
        self.page = max(0, min(self.page, total_pages - 1))
        
        start_index = self.page * MAX_PAGE_SIZE
        end_index = start_index + MAX_PAGE_SIZE
        page_esprits = self.filtered_esprits[start_index:end_index]
        
        embed = discord.Embed(
            title=f"📦 {self.author_id}'s Collection",
            description=f"Showing {total_filtered} of {len(self.all_esprits)} total Esprits.",
            color=0xDAA520
        )
        
        if not page_esprits:
            embed.description += "\n\nNo Esprits match the current filters."
        
        # Get configs with readable variable names
        prog_cfg = self.bot.config.get("progression_settings", {}).get("progression", {})
        power_cfg = self.bot.config.get("combat_settings", {}).get("power_calculation", {})
        stat_cfg = self.bot.config.get("combat_settings", {}).get("stat_calculation", {})

        for ue in page_esprits:
            power = ue.calculate_power(power_cfg, stat_cfg)
            embed.add_field(
                name=f"{self._get_rarity_emoji(ue.esprit_data.rarity)} {ue.esprit_data.name}",
                value=f"ID `{ue.id}` | Lvl **{ue.current_level}/{ue.get_level_cap(prog_cfg)}** | Sigil **{power:,}**",
                inline=False
            )
        
        embed.set_footer(text=f"Page {self.page + 1}/{total_pages} • Sorting by {self.sort_by.name.title()}")
        return embed

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self._get_page_embed(), view=self)

    async def send(self, interaction: discord.Interaction, ephemeral: bool = False):
        """Sends the initial message for the view."""
        self._apply_filters_and_sort()
        embed = self._get_page_embed()
        await interaction.followup.send(embed=embed, view=self, ephemeral=ephemeral)