# src/views/shared/confirmation_view.py
from typing import Optional
import discord

class ConfirmationView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.value: Optional[bool] = None

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.author_id:
            await i.response.send_message("This isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, i: discord.Interaction, _: discord.ui.Button):
        self.value = True
        self.stop()
        await i.response.edit_message(content="✅ Confirmed.", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, i: discord.Interaction, _: discord.ui.Button):
        self.value = False
        self.stop()
        await i.response.edit_message(content="❌ Cancelled.", view=None, embed=None)