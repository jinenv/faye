# src/cogs/esprit_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.db import get_session
from src.database.models import UserEsprit
from src.utils.logger import get_logger

logger = get_logger(__name__)

class CollectionView(discord.ui.View):
    def __init__(self, pages, author_id):
        super().__init__(timeout=120)
        self.pages = pages
        self.author_id = author_id
        self.current_page = 0
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot control this view.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(self.pages) - 1

    async def show_page(self, interaction: discord.Interaction):
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        await self.show_page(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        await self.show_page(interaction)

@app_commands.guild_only()
class EspritGroup(app_commands.Group, name="esprit"):
    """Commands for viewing and managing your Esprits."""

    async def _get_collection_pages(self, user_id: str, username: str) -> list[discord.Embed] | discord.Embed:
        async with get_session() as session:
            stmt = select(UserEsprit).where(UserEsprit.owner_id == user_id).options(selectinload(UserEsprit.esprit_data)).order_by(UserEsprit.esprit_data_id)
            owned_esprits = (await session.execute(stmt)).scalars().all()

        if not owned_esprits:
            return discord.Embed(description="You don't own any Esprits yet. Use `/summon` to get some!", color=discord.Color.light_grey())

        pages = []
        chunk_size = 10
        for i in range(0, len(owned_esprits), chunk_size):
            chunk = owned_esprits[i:i + chunk_size]
            embed = discord.Embed(title=f"{username}'s Esprit Collection", description=f"Page {len(pages) + 1}/{(len(owned_esprits) - 1) // chunk_size + 1}", color=discord.Color.dark_gold())
            for ue in chunk:
                esprit_name = ue.esprit_data.name if ue.esprit_data else "Unknown"
                rarity = ue.esprit_data.rarity if ue.esprit_data else "Unknown"
                embed.add_field(name=f"**{esprit_name}** ({rarity})", value=f"ID: `{ue.id}`", inline=False)
            pages.append(embed)
        return pages
    
    @app_commands.command(name="collection", description="View all Esprits you own.")
    async def collection(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await self._get_collection_pages(str(interaction.user.id), interaction.user.display_name)
        if isinstance(result, discord.Embed):
            await interaction.followup.send(embed=result)
        else:
            view = CollectionView(result, interaction.user.id)
            await interaction.followup.send(embed=result[0], view=view)

class EspritCog(commands.Cog):
    """Player-facing commands for managing Esprits."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Add the slash command group to the bot's command tree
        self.bot.tree.add_command(EspritGroup())

async def setup(bot: commands.Bot):
    await bot.add_cog(EspritCog(bot))