# src/cogs/help_v2_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

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
            row=0,  # V2: Explicit row positioning
        )

    async def callback(self, interaction: discord.Interaction):
        module_id = self.values[0]
        module_data = self.modules[module_id]

        embed = discord.Embed(
            title=f"{module_data['emoji']} {module_data['name']}",
            description=f"**{module_data['description']}**\n\n",
            color=module_data["color"],
        )

        # Enhanced command formatting
        commands_text = ""
        for cmd in module_data["commands"]:
            commands_text += f"**{cmd['cmd']}**\n{cmd['desc']}\n*{cmd.get('usage', '')}*\n\n"
        
        if commands_text:
            embed.add_field(
                name="📝 Available Commands",
                value=commands_text.strip(),
                inline=False,
            )

        # Pro tips section
        if module_data.get("tips"):
            tips_text = "\n".join([f"• {tip}" for tip in module_data["tips"]])
            embed.add_field(
                name="💡 Pro Tips", value=tips_text, inline=False
            )

        # Dynamic thumbnail
        if module_data.get("thumbnail"):
            embed.set_thumbnail(url=module_data["thumbnail"])
            
        embed.set_footer(
            text=f"💫 Use dropdown to explore • {len(self.modules)} modules available",
            icon_url=interaction.client.user.avatar.url if interaction.client.user.avatar else None
        )

        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class QuickActionButton(discord.ui.Button):
    """Quick action buttons for common help actions."""
    def __init__(self, label: str, emoji: str, action: str, style: discord.ButtonStyle = discord.ButtonStyle.secondary):
        super().__init__(
            label=label,
            emoji=emoji,
            style=style,
            row=1  # V2: Second row for action buttons
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        if self.action == "quick_start":
            embed = discord.Embed(
                title="🚀 Quick Start Guide",
                description=(
                    "**New to Nyxa? Follow these steps:**\n\n"
                    "1️⃣ **`/start`** - Create your account & get your first Epic Esprit\n"
                    "2️⃣ **`/daily`** - Claim your daily gold reward (100 gold)\n"
                    "3️⃣ **`/summon 1`** - Try your first summon with beautiful art\n"
                    "4️⃣ **`/esprit collection`** - View your growing collection\n"
                    "5️⃣ **`/help`** - Return here to explore more features!\n\n"
                    "🎯 **Goal:** Collect rare Esprits and build your power!"
                ),
                color=0x00ff00
            )
        elif self.action == "support":
            embed = discord.Embed(
                title="🆘 Get Support & Links",
                description=(
                    "**Need help? We've got you covered:**\n\n"
                    "🌐 **Website:** https://nyxa.bot\n"
                    "💬 **Discord:** Join our support server below\n"
                    "📧 **Contact:** support@nyxa.bot\n"
                    "🐛 **Bug Reports:** Use support server\n"
                    "💡 **Suggestions:** We love feedback!\n\n"
                    "**Average response time: Under 2 hours**"
                ),
                color=0x0077be
            )
        elif self.action == "stats":
            embed = discord.Embed(
                title="📊 Live Nyxa Statistics",
                description="**Real-time bot performance:**\n\n",
                color=0x9d4edd
            )
            # You can wire these to your actual stats later
            embed.add_field(name="👥 Active Users", value="Growing Daily", inline=True)
            embed.add_field(name="🔮 Esprits Summoned", value="Thousands", inline=True) 
            embed.add_field(name="🌍 Servers", value=f"{len(interaction.client.guilds)}", inline=True)
            embed.add_field(name="💰 Economy", value="Thriving", inline=True)
            embed.add_field(name="⚔️ Combat", value="Coming Soon™", inline=True)
            embed.add_field(name="🏪 Marketplace", value="In Development", inline=True)
            
        await interaction.response.edit_message(embed=embed, view=self.view)

class HomeButton(discord.ui.Button):
    """Return to main help menu."""
    def __init__(self, parent_view: 'HelpView'):
        self.parent_view = parent_view
        super().__init__(
            label="Home",
            emoji="🏠",
            style=discord.ButtonStyle.primary,
            row=2  # V2: Third row for navigation
        )

    async def callback(self, interaction: discord.Interaction):
        home_embed = self.parent_view.create_main_embed()
        await interaction.response.edit_message(embed=home_embed, view=self.parent_view)

class HelpView(discord.ui.View):
    """Main view with V2 multi-row component layout."""
    def __init__(self, modules: Dict, author_id: int, bot_avatar_url: Optional[str]):
        super().__init__(timeout=300)
        self.modules = modules
        self.author_id = author_id
        self.bot_avatar_url = bot_avatar_url

        # V2: Multi-row layout organization
        # Row 0: Module selector
        self.add_item(ModuleSelect(self.modules, self))
        
        # Row 1: Quick action buttons
        self.add_item(QuickActionButton("🚀 Quick Start", "🚀", "quick_start", discord.ButtonStyle.success))
        self.add_item(QuickActionButton("🆘 Support", "🆘", "support", discord.ButtonStyle.primary))
        self.add_item(QuickActionButton("📊 Stats", "📊", "stats", discord.ButtonStyle.secondary))
        
        # Row 2: Navigation + external links
        self.add_item(HomeButton(self))
        self.add_item(discord.ui.Button(
            label="Website",
            emoji="🌐",
            style=discord.ButtonStyle.link,
            url="https://nyxa.bot",
            row=2
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
        if hasattr(self, 'message') and self.message:
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass  # Message was deleted

    def create_main_embed(self) -> discord.Embed:
        """Creates the main help embed with V2 enhanced formatting."""
        embed = discord.Embed(
            title="🌟 Nyxa Help Center",
            description=(
                "Welcome to **Nyxa** - *The Next Evolution of Discord Engagement!*\n\n"
                "🎮 **What is Nyxa?**\n"
                "An advanced Discord RPG featuring stunning Esprit collection, "
                "strategic combat, and a thriving cross-server economy.\n\n"
                "**🔥 Key Features:**\n"
                "• Beautiful dynamically-generated Esprit cards\n"
                "• Cross-server progression and trading\n"
                "• Turn-based strategic combat (coming soon)\n"
                "• Rich multi-currency economic system\n\n"
                "**👇 Select a module below to explore!**"
            ),
            color=0xffd60a
        )
        
        # V2: Organized quick reference fields
        embed.add_field(name="🎯 New Player?", value="Try **🚀 Quick Start**", inline=True)
        embed.add_field(name="🔮 Ready to Play?", value="Select **✨ Summoning**", inline=True)
        embed.add_field(name="💰 Need Help?", value="Click **🆘 Support**", inline=True)

        if self.bot_avatar_url:
            embed.set_thumbnail(url=self.bot_avatar_url)
        
        embed.set_footer(text="💫 Tip: Your progress syncs across all servers! • Menu times out in 5 minutes")
        return embed

class HelpV2Cog(commands.Cog):
    """Advanced help system with V2 components and enhanced UX."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Enhanced module data with more detail
        self.modules = {
            "getting_started": {
                "name": "🚀 Getting Started",
                "emoji": "🚀",
                "description": "New to Nyxa? Perfect place to begin your journey!",
                "color": 0x00ff00,
                "commands": [
                    {"cmd": "/start", "desc": "🎯 Begin your adventure", "usage": "Get your first Epic Esprit and 1000 starting gold"},
                    {"cmd": "/balance", "desc": "💰 Check your gold", "usage": "See your current summoning currency"},
                    {"cmd": "/inventory", "desc": "📦 View your items", "usage": "Check dust, fragments, and loot chests"},
                ],
                "tips": [
                    "💡 Your first Esprit is always Epic rarity!",
                    "🎁 You start with 1000 gold for summoning",
                    "🌐 Progress syncs across all servers with Nyxa",
                ]
            },
            "summoning": {
                "name": "✨ Summoning System",
                "emoji": "✨",
                "description": "Collect stunning Esprits with advanced gacha mechanics",
                "color": 0xff6b9d,
                "commands": [
                    {"cmd": "/summon amount:1", "desc": "🎲 Single summon", "usage": "100 gold for one beautiful Esprit card"},
                    {"cmd": "/summon amount:10", "desc": "🎰 Multi summon", "usage": "1000 gold for 10 Esprits with better rates"},
                ],
                "tips": [
                    "⭐ Rarity rates: Common 60% → Deity 0.1%",
                    "🎨 Every card is dynamically generated with unique art",
                    "🍀 10-pulls have slightly improved luck rates",
                ]
            },
            "collection": {
                "name": "🔮 Esprit Collection",
                "emoji": "🔮",
                "description": "Manage your growing army of powerful Esprits",
                "color": 0x9d4edd,
                "commands": [
                    {"cmd": "/esprit collection", "desc": "📚 Browse collection", "usage": "View all owned Esprits with pagination"},
                    {"cmd": "/esprit info [id]", "desc": "🔍 Detailed view", "usage": "See stats, art, and lore of specific Esprit"},
                ],
                "tips": [
                    "🗂️ Collection auto-sorts by rarity and ID",
                    "🆔 Each Esprit has a unique permanent ID",
                    "📊 View detailed combat stats and abilities",
                ]
            },
            "economy": {
                "name": "💰 Economy System",
                "emoji": "💰",
                "description": "Master the multi-currency economic ecosystem",
                "color": 0xffd60a,
                "commands": [
                    {"cmd": "/daily", "desc": "☀️ Daily rewards", "usage": "Claim 100 free gold every 24 hours"},
                    {"cmd": "/balance", "desc": "💳 Check balance", "usage": "View current gold amount"},
                    {"cmd": "/inventory", "desc": "🎒 Full inventory", "usage": "See all currencies and items"},
                ],
                "tips": [
                    "💎 Gold: Primary summoning currency",
                    "✨ Dust: Used for Esprit upgrades (coming soon)",
                    "🔥 Fragments: Crafting rare materials",
                ]
            },
            "combat": {
                "name": "⚔️ Combat System",
                "emoji": "⚔️",
                "description": "Strategic battles await! (In active development)",
                "color": 0xff0000,
                "commands": [
                    {"cmd": "🚧 /battle pve", "desc": "🤖 Fight AI opponents", "usage": "Challenge computer enemies for rewards"},
                    {"cmd": "🚧 /battle pvp", "desc": "👤 Player vs Player", "usage": "Battle other Nyxa users strategically"},
                    {"cmd": "🚧 /team setup", "desc": "🛡️ Formation strategy", "usage": "Arrange Esprits for optimal combat"},
                ],
                "tips": [
                    "⚡ Turn-based tactical combat system",
                    "🎯 Use Esprit stats and abilities strategically",
                    "🏆 Win battles to earn XP, gold, and rare items",
                ]
            },
            "advanced": {
                "name": "🎮 Advanced Features",
                "emoji": "🎮",
                "description": "Master-level gameplay systems and features",
                "color": 0x0077be,
                "commands": [
                    {"cmd": "🔜 /marketplace", "desc": "🏪 Trade with players", "usage": "Buy and sell Esprits globally"},
                    {"cmd": "🔜 /explore", "desc": "🗺️ Adventure mode", "usage": "Discover resources and rare items"},
                    {"cmd": "🔜 /leaderboard", "desc": "🏅 Global rankings", "usage": "Compete with players worldwide"},
                ],
                "tips": [
                    "🌍 Cross-server marketplace for global trading",
                    "🔍 Exploration yields rare crafting materials",
                    "📈 Multiple leaderboard categories and seasons",
                ]
            }
        }

    @app_commands.command(name="helpv2", description="📚 Advanced help system with enhanced Components V2")
    async def help_v2(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        bot_avatar_url = interaction.client.user.avatar.url if interaction.client.user.avatar else None
        view = HelpView(self.modules, interaction.user.id, bot_avatar_url)
        embed = view.create_main_embed()

        # Store message reference for timeout handling
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpV2Cog(bot))
    logger.info("✅ HelpV2Cog loaded")