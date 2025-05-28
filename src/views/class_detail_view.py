import discord
from discord.ui import View, Button
from discord.ext import commands # Needed for bot type hint
from src.database.db import get_session
from src.database.models import User
from src.utils.logger import Logger
from src.utils.image_utils import render_class_selection_page_image, render_class_detail_image # Needed for 'Go Back' & detail image
from src.utils.render_helpers import get_image_as_discord_file

# --- IMPORTANT: Circular Import Note ---
# This import is done in the go_back method to prevent circular dependency at module load.
# from src.views.class_selection_views import ClassSelectionPaginatorView


class ClassDetailView(View):
    """
    A Discord UI View that displays detailed information about a selected class
    and allows the user to either confirm their class choice or navigate back
    to the main class selection paginator.
    """
    def __init__(self, class_id: str, class_info: dict, bot: commands.Bot, original_paginator_message: discord.Message, initial_interaction_user_id: int):
        super().__init__(timeout=180) # 3 minutes timeout for detail screen
        self.class_id = class_id
        self.class_info = class_info
        self.bot = bot
        self.log = Logger(__name__)
        self.original_paginator_message = original_paginator_message # The message to go back to and edit
        self.user_id = initial_interaction_user_id # Original user ID for interaction_check

        # Add the two buttons for this view
        self.add_item(Button(label=f"Choose {class_info['name']}", style=discord.ButtonStyle.success, custom_id=f"confirm_class_{class_id}"))
        self.add_item(Button(label="Go Back to Choices", style=discord.ButtonStyle.danger, custom_id="go_back_to_selection"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensures only the original user who initiated the /start command can interact with this view."""
        if self.user_id and interaction.user.id != self.user_id:
            forbidden_embed = discord.Embed(
                title="Forbidden Interaction 🔒",
                description="This celestial tapestry of choice is not woven for your hands. Only the original seeker may engage.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=forbidden_embed, ephemeral=True)
            return False
        return True


    @discord.ui.button(label="Choose This Class", style=discord.ButtonStyle.success, custom_id="confirm_class_btn", row=0)
    async def confirm_choice(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handles the user's final confirmation of their class choice."""
        # Defer the interaction immediately as database operations can take time
        await interaction.response.defer()

        chosen_class_info = self.class_info # Use stored class_info

        async with get_session() as session:
            user_profile = await session.get(User, str(interaction.user.id))
            if not user_profile:
                self.log.error(f"User profile not found for {interaction.user.id} during class confirmation. This shouldn't happen.")
                error_embed = discord.Embed(
                    title="Cosmic Anomaly Detected ⚠️",
                    description="The threads of your existence are momentarily lost. Please try the `/start` command again.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            if user_profile.class_name: # Safety check: already has a class
                already_chosen_embed = discord.Embed(
                    title="Path Already Forged 🌌",
                    description=f"Your soul is already bound to the path of the **{user_profile.class_name}**. A new path cannot be chosen.",
                    color=discord.Color.dark_grey()
                )
                await interaction.followup.send(embed=already_chosen_embed, ephemeral=True)
                return

            user_profile.class_name = chosen_class_info["name"]
            session.add(user_profile)
            await session.commit()
            await session.refresh(user_profile)
            self.log.info(f"User {interaction.user.id} chose class: {chosen_class_info['name']}.")

        # Disable all buttons and confirm the choice
        for item in self.children:
            item.disabled = True

        confirmation_embed = discord.Embed(
            title=f"✨ Path Chosen! Welcome, {chosen_class_info['name']}! ✨",
            description=f"The cosmic weave shifts to embrace your choice. You are now a **{chosen_class_info['name']}**.\n\n"
                        "Your epic journey has officially begun! Prepare for quests, companions, and the unfolding mysteries of Project X.",
            color=discord.Color.green()
        )
        confirmation_embed.set_footer(text="~ Nyxa's gaze rests upon you ~")

        # Edit the original message that the paginator (ClassSelectionPaginatorView) sent
        if self.original_paginator_message:
            await self.original_paginator_message.edit(embed=confirmation_embed, view=self, attachments=[])
        else: # Fallback if original message wasn't passed (less ideal)
            await interaction.followup.send(embed=confirmation_embed, view=self, files=[]) # Send as new ephemeral message if no original

        self.stop() # End this view (ClassDetailView)


    @discord.ui.button(label="Go Back to Choices", style=discord.ButtonStyle.danger, custom_id="go_back_btn", row=0)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handles navigating back to the main class selection paginator."""
        # Defer the interaction immediately
        await interaction.response.defer()

        # --- CIRCULAR IMPORT FIX: Import ClassSelectionPaginatorView here ---
        from src.views.class_selection_views import ClassSelectionPaginatorView

        # Create a new instance of the paginator view, ensuring it's on the correct page.
        # We assume for simplicity that 'Go Back' always returns to the first page (index 0) of the paginator.
        paginator_view_instance = ClassSelectionPaginatorView(self.bot, initial_interaction_user_id=self.user_id)
        paginator_view_instance.current_page = 0 # Force to first page on 'Go Back'
        paginator_view_instance.update_view_items() # Ensure buttons are updated for page 0

        # Get the embed and image for the first page of the paginator
        page_embed, page_image_file = await paginator_view_instance.get_page_image_and_embed()

        # Edit the original message (stored as self.original_paginator_message)
        if self.original_paginator_message:
            await self.original_paginator_message.edit(
                embed=page_embed,
                view=paginator_view_instance, # Attach the new paginator view instance
                attachments=[page_image_file] if page_image_file else []
            )
            self.stop() # End the current ClassDetailView
        else:
            self.log.error("Original paginator message not found for 'Go Back' action. Sending new ephemeral.")
            await interaction.followup.send(
                embed=page_embed,
                view=paginator_view_instance,
                files=[page_image_file] if page_image_file else [],
                ephemeral=True # Send as a new ephemeral if original message isn't available
            )
            self.stop() # End the current ClassDetailView


    async def on_timeout(self):
        """Disables buttons and updates the message when the view times out."""
        # The message to edit is the one this view is currently attached to, which is the original paginator message.
        if self.message: # 'message' is not directly set for this view's instance, use original_paginator_message
            message_to_edit = self.original_paginator_message
            if message_to_edit:
                current_embed = message_to_edit.embeds[0] if message_to_edit.embeds else discord.Embed(title="🌌 Portal to Details Closed 🌌", color=discord.Color.dark_red())
                current_embed.description = "The celestial information fades. This detail portal has closed."
                current_embed.clear_fields()
                current_embed.set_image(url=None)

                for item in self.children:
                    item.disabled = True # Disable buttons on timeout

                await message_to_edit.edit(embed=current_embed, view=self)