# src/views/esprit/select_view.py
from typing import List, Optional
import discord
from src.database.models import UserEsprit

class EspritSelect(discord.ui.Select):
    """A select menu for choosing one of your Esprits."""
    def __init__(self, esprits: List[UserEsprit]):
        options = [
            discord.SelectOption(
                label=f"{e.esprit_data.name} (Lvl {e.current_level})", value=str(e.id), description=f"ID: {e.id[:6]}")
            for e in esprits[:25]
        ]
        super().__init__(placeholder="Choose an Esprit...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.chosen_esprit_id = self.values[0]
        self.view.stop()
        await interaction.response.defer()

class EspritSelectView(discord.ui.View):
    def __init__(self, esprits: List[UserEsprit], author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.chosen_esprit_id: Optional[str] = None
        self.add_item(EspritSelect(esprits))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id