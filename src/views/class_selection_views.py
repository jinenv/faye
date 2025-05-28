import discord
from discord.ui import View, Button
from src.database.db import get_session
from src.database.models import User
from src.utils.logger import Logger
from src.utils.config_manager import ConfigManager
from src.utils.image_utils import render_class_selection_page_image, render_class_detail_image
from src.utils.render_helpers import get_image_as_discord_file

from src.views.class_detail_view import ClassDetailView

class ClassSelectionPaginatorView(View):
    """
    A Discord UI View that provides a paginated class selection interface for users.
    This view displays a set of class options per page, allowing users to navigate between pages and select a class to view its details. Only the user who initiated the interaction can use the view. The view supports navigation buttons, class selection buttons, and displays class information with custom images and embeds. Handles edge cases such as forbidden interactions, already chosen classes, and navigation limits with informative embed messages. On timeout, disables all buttons and updates the embed to indicate closure.
    Args:
        bot: The Discord bot instance.
        initial_interaction_user_id (Optional[int]): The ID of the user who initiated the interaction; only this user can interact with the view.
    Attributes:
        bot: The Discord bot instance.
        log: Logger for this view.
        class_data: Dictionary containing class information loaded from configuration.
        class_ids: List of class IDs available for selection.
        classes_per_page: Number of classes displayed per page.
        total_pages: Total number of pages based on available classes.
        current_page: The currently displayed page index.
        user_id: The ID of the user allowed to interact with the view.
        message: The Discord message associated with this view.
    Methods:
        interaction_check(interaction): Ensures only the original user can interact; sends an embed if not.
        get_page_image_and_embed(): Generates the embed and image file for the current page.
        update_view_items(): Updates the view's buttons based on the current page.
        on_class_select(interaction): Handles class selection, shows details, and prevents re-selection.
        navigate_next(interaction): Moves to the next page, updating the embed and buttons.
        navigate_prev(interaction): Moves to the previous page, updating the embed and buttons.
        on_timeout(): Disables all buttons and updates the embed to indicate the view has timed out.
    """
    def __init__(self, bot, initial_interaction_user_id=None):
        super().__init__(timeout=300) # 5 minutes timeout
        self.bot = bot
        self.log = Logger(__name__)
        self.class_data = ConfigManager.get_config('config', 'class_data.json')
        self.class_ids = list(self.class_data.keys())
        self.classes_per_page = 2 # Set to 2 classes per page

        # --- DEBUG PRINTS ---
        self.log.info(f"DEBUG_PAG: Initializing Paginator. class_data.keys(): {list(self.class_data.keys())}")
        self.log.info(f"DEBUG_PAG: len(self.class_ids): {len(self.class_ids)}")
        self.total_pages = (len(self.class_ids) + self.classes_per_page - 1) // self.classes_per_page
        self.log.info(f"DEBUG_PAG: Calculated total_pages: {self.total_pages}")
        # --- END DEBUG PRINTS ---
        self.current_page = 0

        if initial_interaction_user_id:
            self.user_id = initial_interaction_user_id
        else:
            self.user_id = None
            self.log.warning("PaginatorView initialized without initial_interaction_user_id.")

        self.message = None # This will be set by the calling cog (src/cogs/start.py)

        self.update_view_items() # Add initial buttons


    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id and interaction.user.id != self.user_id:
            forbidden_embed = discord.Embed(
                title="Forbidden Interaction 🔒",
                description="This celestial tapestry of choice is not woven for your hands. Only the original seeker may engage.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=forbidden_embed, ephemeral=True)
            return False
        return True


    async def get_page_image_and_embed(self):
        start_index = self.current_page * self.classes_per_page
        end_index = start_index + self.classes_per_page
        current_page_class_ids = self.class_ids[start_index:end_index]

        # --- FIX HERE: Call render_class_selection_page_image in executor ---
        page_image_pil = await self.bot.loop.run_in_executor(
            None, render_class_selection_page_image, current_page_class_ids
        )
        # --- END FIX ---

        page_image_file = None
        embed_image_url = None
        if page_image_pil:
            page_image_file = await get_image_as_discord_file(page_image_pil, f"class_selection_page_{self.current_page + 1}.png")
            embed_image_url = f"attachment://class_selection_page_{self.current_page + 1}.png"
        else:
            self.log.error(f"Failed to render image for class selection page {self.current_page + 1}. Displaying without image.")

        page_embed = discord.Embed(
            title=f"🌌 Choose Your Path, Wanderer (Page {self.current_page + 1}/{self.total_pages}) 🌌",
            description="Select a class below to gaze upon its mysteries, or navigate to unveil other choices:",
            color=discord.Color.blue()
        )
        if embed_image_url:
            page_embed.set_image(url=embed_image_url)
        page_embed.set_footer(text="~ Nyxa, Weaver of Fates ~")

        return page_embed, page_image_file


    def update_view_items(self):
        """Clears and re-adds all items (class buttons + nav buttons) based on the current page."""
        self.clear_items()

        start_index = self.current_page * self.classes_per_page
        end_index = start_index + self.classes_per_page
        current_page_class_ids = self.class_ids[start_index:end_index]

        # Add class selection buttons (now 2 per page)
        for class_id in current_page_class_ids:
            class_info = self.class_data[class_id]
            button = Button(
                label=class_info["name"],
                style=discord.ButtonStyle.secondary,
                custom_id=f"select_class_{class_id}"
            )
            button.callback = self.on_class_select
            self.add_item(button)

        # Add navigation buttons (if more than one page)
        if self.total_pages > 1:
            # Previous button
            prev_button = Button(
                label="⬅️ Previous",
                style=discord.ButtonStyle.blurple,
                custom_id="navigate_prev_btn",
                row=4, # Forces it to a new row
                disabled=(self.current_page == 0) # Disable if on first page
            )
            prev_button.callback = self.navigate_prev
            self.add_item(prev_button)

            # Next button
            next_button = Button(
                label="Next ➡️",
                style=discord.ButtonStyle.blurple,
                custom_id="navigate_next_btn",
                row=4, # Forces it to a new row
                disabled=(self.current_page == self.total_pages - 1) # Disable if on last page
            )
            next_button.callback = self.navigate_next
            self.add_item(next_button)


    async def on_class_select(self, interaction: discord.Interaction):
        # Acknowledge the interaction immediately
        await interaction.response.defer()

        # --- DEBUG PRINTS ---
        self.log.info(f"DEBUG_INT: Interaction type: {type(interaction)}")
        self.log.info(f"DEBUG_INT: Interaction data: {interaction.data}")
        if hasattr(interaction, 'custom_id'):
            self.log.info(f"DEBUG_INT: Interaction has custom_id: {interaction.custom_id}")
        else:
            self.log.error("DEBUG_INT: Interaction DOES NOT have custom_id attribute (expected for button click).")
        # --- END DEBUG PRINTS ---

        # FIX: Access custom_id from interaction.data dictionary
        try:
            class_id = interaction.data['custom_id'].replace("select_class_", "")
            self.log.info(f"DEBUG_INT: Successfully extracted class_id: {class_id}")
        except KeyError:
            self.log.error("DEBUG_INT: 'custom_id' not found in interaction.data. This is unexpected for a button click, abandoning.")
            error_embed = discord.Embed(
                title="Cosmic Anomaly Detected ⚠️",
                description="Failed to identify the selected class. Please try selecting a class again. (Custom ID Missing)",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        chosen_class_info = self.class_data.get(class_id)

        if not chosen_class_info:
            error_embed = discord.Embed(
                title="Cosmic Anomaly Detected ⚠️",
                description="A strange ripple in the fabric of choice occurred. Please try selecting a class again. (Class Info Missing)",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        async with get_session() as session:
            user_profile = await session.get(User, str(interaction.user.id))
            if user_profile and user_profile.class_name:
                already_chosen_embed = discord.Embed(
                    title="Path Already Forged 🌌",
                    description=f"Your soul is already bound to the path of the **{user_profile.class_name}**. A new path cannot be chosen.",
                    color=discord.Color.dark_grey()
                )
                await interaction.followup.send(embed=already_chosen_embed, ephemeral=True)
                return

        detail_embed = discord.Embed(
            title=f"📜 {chosen_class_info['name']} Details 📜",
            description=chosen_class_info['description'],
            color=discord.Color.gold()
        )
        detail_embed.add_field(name="Base Stats", value=(
            f"HP: {chosen_class_info['base_hp']}\n"
            f"ATK: {chosen_class_info['base_attack']}\n"
            f"DEF: {chosen_class_info['base_defense']}\n"
            f"SPD: {chosen_class_info['base_speed']}"
        ), inline=True)
        detail_embed.set_footer(text="~ Nyxa, Weaver of Fates ~")

        # Running Pillow rendering in an executor to prevent blocking the event loop
        detail_image_pil = await self.bot.loop.run_in_executor(
            None, render_class_detail_image, class_id
        )
        detail_file = None
        if detail_image_pil:
            detail_file = await get_image_as_discord_file(detail_image_pil, f"{class_id}_details.png")
            detail_embed.set_image(url=f"attachment://{class_id}_details.png")
        else:
            self.log.error(f"Failed to render detail image for {class_id}. Displaying without image.")

        final_selection_view = ClassDetailView(
            class_id=class_id,
            class_info=chosen_class_info,
            bot=self.bot,
            original_paginator_message=interaction.message,
            initial_interaction_user_id=self.user_id
        )

        # Use followup.edit_message or edit the stored message
        if self.message:
             await self.message.edit(embed=detail_embed, view=final_selection_view, attachments=[detail_file] if detail_file else [])
        else: # Fallback if message wasn't stored (less ideal for pagination)
            await interaction.followup.send(embed=detail_embed, view=final_selection_view, files=[detail_file] if detail_file else [])

    async def navigate_next(self, interaction: discord.Interaction):
        # Acknowledge the interaction within 3 seconds
        await interaction.response.defer()

        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_view_items()

            page_embed, page_image_file = await self.get_page_image_and_embed()

            if self.message: # Ensure message is stored from cog
                await self.message.edit(
                    embed=page_embed,
                    view=self,
                    attachments=[page_image_file] if page_image_file else []
                )
            else: # Fallback if message wasn't stored (less ideal)
                await interaction.followup.send(
                    embed=page_embed,
                    view=self,
                    files=[page_image_file] if page_image_file else []
                )
        else:
            last_page_embed = discord.Embed(
                title="Edge of the Cosmos ✨",
                description="No further choices reside upon this page. You stand at the very frontier of selection.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=last_page_embed, ephemeral=True)


    async def navigate_prev(self, interaction: discord.Interaction):
        # Acknowledge the interaction within 3 seconds
        await interaction.response.defer()

        if self.current_page > 0:
            self.current_page -= 1
            self.update_view_items()

            page_embed, page_image_file = await self.get_page_image_and_embed()

            if self.message: # Ensure message is stored from cog
                await self.message.edit(
                    embed=page_embed,
                    view=self,
                    attachments=[page_image_file] if page_image_file else []
                )
            else: # Fallback if message wasn't stored
                await interaction.followup.send(
                    embed=page_embed,
                    view=self,
                    files=[page_image_file] if page_image_file else []
                )
        else:
            first_page_embed = discord.Embed(
                title="Realm's Genesis 📜",
                description="You are already at the very first glimpse of paths. There is no wisdom to glean beyond this threshold.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=first_page_embed, ephemeral=True)


    async def on_timeout(self):
        # Update the original message if it exists
        if self.message:
            message_to_edit = self.message
            if message_to_edit:
                current_embed = message_to_edit.embeds[0] if message_to_edit.embeds else discord.Embed(title="🌌 Selection Portal Closed 🌌", color=discord.Color.dark_red())
                current_embed.description = "The echoes of choice have faded. This selection portal has closed."
                current_embed.clear_fields()
                current_embed.set_image(url=None)

                for item in self.children:
                    item.disabled = True

                await message_to_edit.edit(embed=current_embed, view=self)