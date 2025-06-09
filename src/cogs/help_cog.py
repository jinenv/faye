# src/cogs/help_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# --- UI Components ---

class ModuleSelect(discord.ui.Select):
    """The dropdown menu for selecting a help module."""
    def __init__(self, modules: Dict, parent_view: 'HelpView'):
        self.modules = modules
        self.parent_view = parent_view

        options = [
            discord.SelectOption(
                label=module_data["name"],
                description=module_data["description"][:100],
                emoji=module_data["emoji"],
                value=module_id,
            )
            for module_id, module_data in modules.items()
        ]

        super().__init__(
            placeholder="🎯 Choose a module to explore...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        module_id = self.values[0]
        await self.parent_view.show_module(interaction, module_id)


class QuickActionButton(discord.ui.Button):
    """Quick action buttons for common help actions."""
    def __init__(self, label: str, emoji: str, action: str, parent_view: 'HelpView', style: discord.ButtonStyle = discord.ButtonStyle.secondary):
        super().__init__(label=label, emoji=emoji, style=style, row=1)
        self.action = action
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if self.action == "quick_start":
            await self.parent_view.show_quick_start(interaction)
        elif self.action == "support":
            await self.parent_view.show_support_info(interaction)
        elif self.action == "stats":
            await self.parent_view.show_bot_stats(interaction)


class HomeButton(discord.ui.Button):
    """Returns the user to the main help menu."""
    def __init__(self, parent_view: 'HelpView'):
        self.parent_view = parent_view
        super().__init__(label="Home", emoji="🏠", style=discord.ButtonStyle.primary, row=2)

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.show_home(interaction)


# --- Main Help View ---

class HelpView(discord.ui.View):
    """Main view with a multi-row layout for the help command."""
    def __init__(self, modules: Dict, author_id: int, bot: commands.Bot):
        super().__init__(timeout=300)
        self.modules = modules
        self.author_id = author_id
        self.bot = bot
        self.message: Optional[discord.InteractionMessage] = None

        # Row 0: Module selector
        self.add_item(ModuleSelect(self.modules, self))
        
        # Row 1: Quick action buttons
        self.add_item(QuickActionButton("🚀 Quick Start", "🚀", "quick_start", self, discord.ButtonStyle.success))
        self.add_item(QuickActionButton("🆘 Support", "🆘", "support", self, discord.ButtonStyle.primary))
        self.add_item(QuickActionButton("📊 Stats", "📊", "stats", self))
        
        # Row 2: Navigation + external links
        self.add_item(HomeButton(self))
        self.add_item(discord.ui.Button(
            label="Website", emoji="🌐", style=discord.ButtonStyle.link,
            url="https://nyxa.bot", row=2
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ This help menu belongs to someone else. Use `/help` to get your own!",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass # Message was deleted

    def create_main_embed(self) -> discord.Embed:
        """Creates the initial, main help embed."""
        embed = discord.Embed(
            title="🌟 Nyxa Help Center",
            description=(
                "Welcome to **Nyxa** - *The Next Evolution of Discord Engagement!*\n\n"
                "An advanced Discord RPG featuring stunning Esprit collection, "
                "strategic combat, and a thriving cross-server economy."
            ),
            color=0xffd60a # Nyxa Gold
        )
        embed.add_field(
            name="🔥 Key Features",
            value=(
                "• Beautiful dynamically-generated Esprit cards\n"
                "• Cross-server progression and economy\n"
                "• Deep, strategic combat system\n"
                "• Rich multi-currency economic system"
            ),
            inline=False
        )
        embed.add_field(
            name="👇 How to Use",
            value="Select a module from the dropdown menu or use the buttons below to learn more.",
            inline=False
        )
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text="Tip: Your progress syncs across all servers! • Menu times out in 5 minutes")
        return embed

    # --- View State Changers ---
    
    async def show_home(self, interaction: discord.Interaction):
        """Displays the main help embed."""
        embed = self.create_main_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_module(self, interaction: discord.Interaction, module_id: str):
        """Displays a specific module's information."""
        module_data = self.modules[module_id]
        embed = discord.Embed(
            title=f"{module_data['emoji']} {module_data['name']}",
            description=f"**{module_data['description']}**\n\n",
            color=module_data["color"],
        )

        commands_text = ""
        for cmd in module_data["commands"]:
            commands_text += f"**`{cmd['cmd']}`**\n{cmd['desc']}\n\n"
        
        if commands_text:
            embed.add_field(name="📝 Commands", value=commands_text.strip(), inline=False)

        if module_data.get("tips"):
            tips_text = "\n".join([f"• {tip}" for tip in module_data["tips"]])
            embed.add_field(name="💡 Pro Tips", value=tips_text, inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_quick_start(self, interaction: discord.Interaction):
        """Displays the quick start guide."""
        embed = discord.Embed(
            title="🚀 Quick Start Guide",
            description=(
                "**New to Nyxa? Follow these steps:**\n\n"
                "1️⃣ **`/start`** - Create your account & get your first Epic Esprit.\n"
                "2️⃣ **`/daily`** - Claim your daily bundle of Nyxies.\n"
                "3️⃣ **`/summon`** - Use your starting Azurites for your first summon!\n"
                "4️⃣ **`/inventory`** - Check all your new currencies.\n"
                "5️⃣ **`/esprit collection`** - View your growing collection.\n\n"
                "🎯 **Your Goal:** Collect rare Esprits, build your power, and explore the world!"
            ),
            color=0x2ECC71 # Emerald Green
        )
        await interaction.response.edit_message(embed=embed, view=self)
        
    async def show_support_info(self, interaction: discord.Interaction):
        """Displays support and contact information."""
        embed = discord.Embed(
            title="🆘 Get Support & Links",
            description=(
                "**Need help? We've got you covered:**\n\n"
                "🌐 **Website:** https://nyxa.bot\n"
                "💬 **Discord:** Join our support server for help & updates.\n"
                "📧 **Contact:** support@nyxa.bot\n\n"
                "Found a bug? Have a suggestion? Let us know in the support server!"
            ),
            color=0x3498DB # Peter River Blue
        )
        await interaction.response.edit_message(embed=embed, view=self)
        
    async def show_bot_stats(self, interaction: discord.Interaction):
        """Displays live bot statistics."""
        embed = discord.Embed(
            title="📊 Live Nyxa Statistics",
            description="Real-time bot performance and game stats:",
            color=0x9B59B6 # Amethyst
        )
        embed.add_field(name="🌍 Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        # TODO: Wire these up to actual database queries later
        embed.add_field(name="👥 Players", value="Coming Soon", inline=True)
        embed.add_field(name="🔮 Esprits Summoned", value="Coming Soon", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)


# --- Cog Definition ---

class HelpCog(commands.Cog, name="Help"):
    """Advanced, directive-compliant help system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # This data is now aligned with our project directive
        self.modules = {
            "core": {
                "name": "🚀 Core Commands", "emoji": "🚀",
                "description": "The essential commands to start your journey.",
                "color": 0x2ECC71, # Emerald Green
                "commands": [
                    {"cmd": "/start", "desc": "Begin your adventure and claim your first Epic Esprit."},
                    {"cmd": "/daily", "desc": "Claim your daily bundle of Nyxies."},
                    {"cmd": "/inventory", "desc": "View all your currencies and materials."},
                ],
                "tips": [
                    "Your first Esprit is always **Epic** rarity!",
                    "Use `/inventory` to see your Azurites, Nyxies, and more.",
                ]
            },
            "summoning": {
                "name": "✨ Summoning", "emoji": "✨",
                "description": "Collect stunning Esprits via the summoning portal.",
                "color": 0xE91E63, # Pink
                "commands": [
                    {"cmd": "/summon", "desc": "Summon new Esprits using your Azurites."},
                ],
                "tips": [
                    "**Azurites** are the sole currency for summoning.",
                    "Earn **Azurite Shards** from gameplay to form new Azurites.",
                    "Every card is dynamically generated with beautiful, unique art.",
                ]
            },
            "esprit": {
                "name": "🔮 Esprit Management", "emoji": "🔮",
                "description": "Manage, view, and upgrade your powerful Esprits.",
                "color": 0x9B59B6, # Amethyst
                "commands": [
                    {"cmd": "/esprit collection", "desc": "Browse all the Esprits you've collected."},
                    {"cmd": "🔜 /esprit equip <id>", "desc": "Set your active Esprit for your profile."},
                    {"cmd": "� /esprit upgrade <id>", "desc": "Spend Moonglow to level up an Esprit."},
                    {"cmd": "🔜 /esprit team", "desc": "Arrange your 3-Esprit combat team."},
                ],
                "tips": [
                    "Each Esprit has a unique ID, shown in its collection card.",
                    "Your Player Level determines the max level of your Esprits.",
                ]
            },
            "economy": {
                "name": "💰 Economy", "emoji": "💰",
                "description": "Understand Nyxa's multi-currency economic system.",
                "color": 0xFFC107, # Amber
                "commands": [
                    {"cmd": "/inventory", "desc": "The central hub for all your assets."},
                    {"cmd": "🔜 /marketplace", "desc": "Trade Esprits and items with other players."},
                ],
                "tips": [
                    "**<:nyxies_icon:ID> Nyxies:** Universal currency for shops and trading.",
                    "**<:azurite_icon:ID> Azurites:** The premium currency used for summoning.",
                    "**<:moonglow_icon:ID> Moonglow:** Material used to level up your Esprits.",
                    "**<:essence_icon:ID> Essence:** Resources used for crafting and limit breaks.",
                ]
            },
             "progression": {
                "name": "⚔️ Progression", "emoji": "⚔️",
                "description": "Commands to track your growth and power.",
                "color": 0x3498DB, # Peter River
                "commands": [
                    {"cmd": "🔜 /explore", "desc": "Embark on adventures to find rewards."},
                    {"cmd": "🔜 /tower", "desc": "Climb the tower to face powerful bosses."},
                    {"cmd": "🔜 /profile", "desc": "View your complete player profile and stats."},
                    {"cmd": "🔜 /level", "desc": "Check your current level and XP progress."},
                ],
                "tips": [
                    "**/explore** is the main way to earn **Azurite Shards** and **Essence**.",
                    "Your Esprits can only be leveled as high as your player level allows.",
                ]
            },
        }

    @app_commands.command(name="help", description="Open the main Nyxa help center.")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = HelpView(self.modules, interaction.user.id, self.bot)
        embed = view.create_main_embed()
        # Store message reference for timeout handling
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
    logger.info("✅ HelpCog loaded")
