import discord
from discord.ext import commands
from src.database.db import get_session
from src.database.models import User
from src.utils.logger import Logger
from src.utils.config_manager import ConfigManager
from src.utils.image_utils import render_class_selection_page_image
from src.utils.render_helpers import get_image_as_discord_file

from src.views.class_selection_views import ClassSelectionPaginatorView

class StartCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = Logger(__name__)
        self.class_data = ConfigManager.get_config('config', 'class_data.json')
        if not self.class_data:
            self.log.error("Failed to load class_data.json. Class selection might not work.")

    @commands.hybrid_command(
        name="start",
        description="Begin your journey in Project X and choose your class!"
    )
    async def start_command(self, ctx: commands.Context):
        self.log.info(f"User {ctx.author.id} ({ctx.author.name}) used /start command.")

        async with get_session() as session:
            user_profile = await session.get(User, str(ctx.author.id))

            if user_profile and user_profile.class_name:
                self.log.info(f"User {ctx.author.id} already has class: {user_profile.class_name}.")
                already_chosen_embed = discord.Embed(
                    title="Path Already Forged 🌌",
                    description=f"Seek not a new beginning, for your journey as a **{user_profile.class_name}** has already commenced.\n"
                                f"To chart your course, behold your `/profile` or gaze upon your `/collection`.",
                    color=discord.Color.dark_grey()
                )
                await ctx.send(embed=already_chosen_embed, ephemeral=True)
                return

            if not user_profile:
                self.log.info(f"Creating new user profile for {ctx.author.id}.")
                user_profile = User(user_id=str(ctx.author.id), username=ctx.author.name)
                session.add(user_profile)
                await session.commit()
                await session.refresh(user_profile)

        # --- FIX HERE: Dynamically get classes for the first page ---
        # Instantiate the view *before* preparing the image, so we can use its classes_per_page
        # This also ensures the view is initialized with the correct pagination settings from the start.
        view = ClassSelectionPaginatorView(self.bot, initial_interaction_user_id=ctx.author.id)

        first_page_class_ids = view.class_ids[0:view.classes_per_page] # Get the correct number for first page
        # --- END FIX ---

        page_image_pil = await render_class_selection_page_image(first_page_class_ids)
        if page_image_pil:
            image_file = await get_image_as_discord_file(page_image_pil, "class_selection_page_1.png")
            embed_image_url = f"attachment://class_selection_page_1.png"
        else:
            self.log.error(f"Failed to render image for initial /start page. Displaying without image.")
            image_file = None
            embed_image_url = None

        embed = discord.Embed(
            title="🌌 Welcome to Project X, Wanderer! 🌌",
            description="To begin your epic journey, choose your foundational class. Each offers a unique path, etched into the very fabric of this realm.\n\n"
                        "Select a class below to gaze upon its mysteries, or navigate to unveil other choices:",
            color=discord.Color.dark_gold()
        )
        if embed_image_url:
            embed.set_image(url=embed_image_url)
        embed.set_footer(text="~ Nyxa, Weaver of Fates ~")


        # The view is already instantiated above
        initial_message = await ctx.send(
            embed=embed,
            view=view,
            files=[image_file] if image_file else [],
            ephemeral=False
        )
        view.message = initial_message

    @commands.hybrid_command(name="ping", description="Checks if the bot is alive!")
    async def ping_command(self, ctx: commands.Context):
        self.log.info(f"User {ctx.author.id} used /ping command.")
        ping_embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: {round(self.bot.latency * 1000)}ms",
            color=discord.Color.blue()
        )
        await ctx.send(embed=ping_embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(StartCog(bot))