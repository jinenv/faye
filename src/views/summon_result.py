# src/views/summon_result.py
import discord
from discord.ui import View, Button

# Corrected import for the logger
from src.utils.logger import get_logger
logger = get_logger(__name__)

class SummonResultView(View):
    def __init__(self, esprit_data_list: list, summon_image_file: discord.File = None, initial_page: int = 0):
        super().__init__()
        self.esprit_data_list = esprit_data_list
        self.summon_image_file = summon_image_file
        self.current_page = initial_page

        # We'll need a way to render the page content dynamically
        # For a simple example, let's just add buttons for now.
        # You'll expand this with proper page rendering and embeds/files.

        # Add navigation buttons if there's more than one Esprit
        if len(self.esprit_data_list) > 1:
            self.add_item(discord.ui.Button(label="⬅️ Previous", style=discord.ButtonStyle.secondary, custom_id="summon_prev_page"))
            self.add_item(discord.ui.Button(label="Next ➡️", style=discord.ButtonStyle.secondary, custom_id="summon_next_page"))

        # Add a "Claim All" or "Done" button
        self.add_item(discord.ui.Button(label="✅ Done", style=discord.ButtonStyle.success, custom_id="summon_done"))

    async def _update_message_content(self, interaction: discord.Interaction):
        # This is where you'll dynamically update the embed/image based on self.current_page
        # For now, it's just a placeholder.
        current_esprit_data = self.esprit_data_list[self.current_page]
        embed = discord.Embed(
            title=f"Your Summon Result - {current_esprit_data['name']}",
            description=f"Rarity: {current_esprit_data['rarity']}\n{current_esprit_data['description']}",
            color=discord.Color.blue() # You'll likely use rarity-based colors here
        )
        # If you generated a single image per summon for the first result, you'd send it here.
        # For a multi-page view, you might re-render or just use embeds.
        # For now, if self.summon_image_file exists, it implies it's the initial one.
        # For subsequent pages, you'd generate new images or just rely on embeds.

        # This will be more complex when you integrate the actual image generation for multi-page views
        # and dynamic updates. For /start, it's simpler.

        # To keep it simple for now, we'll just update the embed.
        # If you have specific image rendering for each page, you'd put it here.
        # For now, let's assume the image is part of the initial message for simplicity with /start.
        # Or, you'd generate a new image for each page here.

        await interaction.response.edit_message(embed=embed, view=self)


    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary, custom_id="summon_prev_page", row=0)
    async def prev_page_button(self, interaction: discord.Interaction, button: Button):
        self.current_page = (self.current_page - 1) % len(self.esprit_data_list)
        logger.info(f"Navigating to page {self.current_page} for summon result.")
        await self._update_message_content(interaction)
        # Ensure buttons are re-enabled/disabled based on page if needed, but not strictly necessary for wrap-around logic

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary, custom_id="summon_next_page", row=0)
    async def next_page_button(self, interaction: discord.Interaction, button: Button):
        self.current_page = (self.current_page + 1) % len(self.esprit_data_list)
        logger.info(f"Navigating to page {self.current_page} for summon result.")
        await self._update_message_content(interaction)
        # Ensure buttons are re-enabled/disabled based on page if needed

    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.success, custom_id="summon_done", row=1)
    async def done_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Summon results viewed! Your new Esprits are ready for adventure.", ephemeral=True)
        self.stop() # Stop the view to disable buttons
        logger.info(f"Summon result view stopped by {interaction.user.display_name}.")