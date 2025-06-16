# src/views/esprit/dissolve_view.py
from typing import List, Set
import discord
from src.database.models import UserEsprit
from src.views.shared.confirmation_view import ConfirmationView

MAX_DISSOLVE_PAGE_SIZE = 25
INTERACTION_TIMEOUT = 300

class BulkDissolveView(discord.ui.View):
    """Interactive multi-dissolve selection with pagination."""
    def __init__(self, esprits: List[UserEsprit], author_id: int):
        super().__init__(timeout=INTERACTION_TIMEOUT)
        self.all_esprits, self.author_id, self.selected_ids = esprits, author_id, set()
        self.page, self.max_pages = 0, (len(esprits) + MAX_DISSOLVE_PAGE_SIZE - 1) // MAX_DISSOLVE_PAGE_SIZE
        self.value = False
        self._setup_components()

    def _get_rarity_emoji(self, rarity: str) -> str:
        return {"Common":"⚪","Uncommon":"🟢","Rare":"🔵","Epic":"🟣","Celestial":"🟡","Supreme":"🔴","Deity":"🌟"}.get(rarity,"❓")

    def _setup_components(self):
        self.select_menu = discord.ui.Select(placeholder="Select Esprits...", min_values=0, max_values=MAX_DISSOLVE_PAGE_SIZE, row=0)
        self.prev_button = discord.ui.Button(label="◀️", style=discord.ButtonStyle.secondary, row=1)
        self.next_button = discord.ui.Button(label="▶️", style=discord.ButtonStyle.secondary, row=1)
        self.dissolve_button = discord.ui.Button(label="Dissolve Selected", style=discord.ButtonStyle.danger, disabled=True, row=2)
        
        self.select_menu.callback = self.on_select
        self.prev_button.callback = self.go_prev
        self.next_button.callback = self.go_next
        self.dissolve_button.callback = self.on_dissolve

        self.add_item(self.select_menu)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.dissolve_button)
        self._refresh_view()

    def _refresh_view(self):
        start, end = self.page * MAX_DISSOLVE_PAGE_SIZE, (self.page + 1) * MAX_DISSOLVE_PAGE_SIZE
        self.select_menu.placeholder = f"Page {self.page + 1}/{self.max_pages or 1}..."
        self.select_menu.options = [
            discord.SelectOption(
                label=f"{e.esprit_data.name} • Lvl {e.current_level}", value=str(e.id), emoji=self._get_rarity_emoji(e.esprit_data.rarity),
                description=f"ID: {e.id[:6]}", default=str(e.id) in self.selected_ids)
            for e in self.all_esprits[start:end]
        ]
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.max_pages - 1
        self.dissolve_button.disabled = not self.selected_ids
        self.dissolve_button.label = f"Dissolve ({len(self.selected_ids)}) Selected" if self.selected_ids else "Dissolve Selected"

    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id: await inter.response.send_message("This is not for you.", ephemeral=True); return False
        return True

    async def go_prev(self, inter: discord.Interaction):
        if self.page > 0: self.page -= 1
        self._refresh_view(); await inter.response.edit_message(view=self)

    async def go_next(self, inter: discord.Interaction):
        if self.page < self.max_pages - 1: self.page += 1
        self._refresh_view(); await inter.response.edit_message(view=self)

    async def on_select(self, inter: discord.Interaction):
        current_page_ids = {o.value for o in self.select_menu.options}
        self.selected_ids -= current_page_ids
        self.selected_ids.update(inter.data.get("values", []))
        self._refresh_view(); await inter.response.edit_message(view=self)

    async def on_dissolve(self, inter: discord.Interaction):
        confirm = ConfirmationView(self.author_id)
        await inter.response.send_message(
            embed=discord.Embed(title="⚠️ Confirm Bulk Dissolve", description=f"Dissolve **{len(self.selected_ids)}** Esprit(s)? This is final.", color=discord.Color.red()),
            view=confirm, ephemeral=True)
        await confirm.wait()
        if confirm.value:
            self.value = True; self.stop()
            await inter.edit_original_response(content="Processing dissolve...", view=None, embed=None)