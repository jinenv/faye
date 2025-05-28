import uuid
import discord
from discord.ui import View, Button
from discord.ext import commands # For bot type hinting
from src.database.db import get_session
from src.database.models import User, UserEsprit
from src.utils.logger import Logger

log = Logger(__name__)

class SummonResultView(View):
    """
    A Discord UI View for displaying the result of an Esprit summon.
    Includes a button to set the summoned Esprit as the user's active Esprit.
    """
    def __init__(self, bot: commands.Bot, user_id: str, esprit_id: uuid.UUID, esprit_name: str):
        super().__init__(timeout=180) # View times out after 3 minutes
        self.bot = bot
        self.user_id = user_id
        self.esprit_id = esprit_id # This is the unique UUID of the UserEsprit instance
        self.esprit_name = esprit_name # The name of the Esprit type (e.g., "Fire Golem")

        # Add buttons to the view
        # We'll add a "Set as Active" button
        self.add_item(Button(label=f"Set {esprit_name} as Active", style=discord.ButtonStyle.primary, custom_id=f"set_active_esprit_{self.esprit_id}"))
        # A "View Stats" button could also be added, linking to a /profile command
        # self.add_item(Button(label="View Stats", style=discord.ButtonStyle.secondary, custom_id=f"view_esprit_stats_{self.esprit_id}"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensures only the original user can interact with this view."""
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This isn't your summon! Leave it to its rightful owner.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Set as Active", style=discord.ButtonStyle.primary, custom_id="set_active_esprit_button_placeholder_DO_NOT_USE")
    async def set_active_button_callback(self, interaction: discord.Interaction, button: Button):
        """Callback for the 'Set as Active' button."""
        await interaction.response.defer(ephemeral=True) # Defer immediately, response will follow

        try:
            # The actual custom_id carries the esprit_id
            custom_id_parts = button.custom_id.split('_')
            if len(custom_id_parts) < 4:
                raise ValueError("Invalid custom_id format for set_active_esprit button.")

            # Reconstruct the UUID from the custom_id parts if it was split
            # This ensures we get the full UUID even if it contains hyphens
            # The format is "set_active_esprit_{UUID}"
            esprit_instance_uuid_str = "_".join(custom_id_parts[3:]) # Join parts after "set_active_esprit"
            esprit_instance_uuid = uuid.UUID(esprit_instance_uuid_str)

            async with get_session() as session:
                user = await session.get(User, str(interaction.user.id))
                if not user:
                    await interaction.followup.send("Could not find your user profile. Please try the `/start` command again.", ephemeral=True)
                    log.error(f"User {interaction.user.id} not found when trying to set active esprit.")
                    return

                esprit_instance = await session.get(UserEsprit, esprit_instance_uuid)
                if not esprit_instance or str(esprit_instance.owner_id) != str(interaction.user.id):
                    await interaction.followup.send("This Esprit either doesn't exist or doesn't belong to you!", ephemeral=True)
                    log.warning(f"User {interaction.user.id} tried to set non-existent or unowned esprit {esprit_instance_uuid} as active.")
                    return

                user.active_esprit_id = esprit_instance.id # Set the UUID as active
                session.add(user)
                await session.commit()
                await session.refresh(user)

                # Update the button to show it's selected, and disable it
                button.label = f"Active: {esprit_instance.esprit_definition.name if esprit_instance.esprit_definition else self.esprit_name}"
                button.style = discord.ButtonStyle.success
                for item in self.children:
                    item.disabled = True # Disable all buttons on this view once selected

                await interaction.followup.send(f"🌟 **{self.esprit_name}** has been set as your active Esprit!", ephemeral=True)
                await interaction.message.edit(view=self) # Update the original message
                self.stop() # Stop the view as interaction is complete

        except ValueError as ve:
            log.error(f"Error parsing custom_id for set_active_esprit: {ve}", exc_info=True)
            await interaction.followup.send("There was an error setting your active Esprit. Please try again or contact support.", ephemeral=True)
        except Exception as e:
            log.error(f"Unhandled error in SummonResultView set_active_button_callback: {e}", exc_info=True)
            await interaction.followup.send("An unexpected error occurred while setting your active Esprit.", ephemeral=True)

    async def on_timeout(self):
        """Called when the view times out."""
        for item in self.children:
            item.disabled = True
        if self.message: # Assumes the message is set by the cog
            await self.message.edit(view=self)
        log.info(f"SummonResultView for user {self.user_id} timed out.")