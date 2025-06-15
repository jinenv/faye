# src/cogs/help_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, Optional
import random

from src.utils.logger import get_logger

logger = get_logger(__name__)

# --- UI Components ---

class ModuleSelect(discord.ui.Select):
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
    def __init__(self, parent_view: 'HelpView'):
        self.parent_view = parent_view
        super().__init__(label="Home", emoji="🏠", style=discord.ButtonStyle.primary, row=2)

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.show_home(interaction)

# --- Main Help View ---

class HelpView(discord.ui.View):
    def __init__(self, modules: Dict, author_id: int, bot: commands.Bot):
        super().__init__(timeout=300)
        self.modules = modules
        self.author_id = author_id
        self.bot = bot
        self.message: Optional[discord.InteractionMessage] = None
        self.add_item(ModuleSelect(self.modules, self))
        self.add_item(QuickActionButton("🚀 Quick Start", "🚀", "quick_start", self, discord.ButtonStyle.success))
        self.add_item(QuickActionButton("🆘 Support", "🆘", "support", self, discord.ButtonStyle.primary))
        self.add_item(QuickActionButton("📊 Stats", "📊", "stats", self))
        self.add_item(HomeButton(self))
        self.add_item(discord.ui.Button(
            label="Website", emoji="🌐", style=discord.ButtonStyle.link,
            url="https://faye.bot", row=2
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
                pass

    def create_main_embed(self) -> discord.Embed:
        FLAVOR_QUOTES = [
            "“To collect is to remember. To summon is to create.”",
            "“Every Esprit holds a secret. Will you uncover it?”",
            "“Victory favors those who experiment.”",
            "“True strength lies in your collection.”",
            "“The journey is only beginning.”",
            "“Legends aren’t summoned—they’re made.”",
            "“Synergy is the path to supremacy.”",
            "“May the rarest Esprit find you.”",
            "“Faye watches those who dare to summon.”",
            "“Seek, summon, ascend.”",
        ]
        embed = discord.Embed(
            title="✨ Faye Help Center",
            description=(
                "**Collect. Summon. Evolve.**\n"
                "A next-gen Discord RPG—real-time, cross-server, endlessly deep.\n"
            ),
            color=0xffd60a
        )
        embed.add_field(
            name="📖 **Quick Reference**",
            value=(
                "• `/start` — Begin, get starter pack\n"
                "• `/summon` — New Esprit rolls\n"
                "• `/esprit collection` — View your squad\n"
                "• `/inventory` — Currencies/materials\n"
                "• `/profile` — Player stats\n"
            ),
            inline=False
        )
        embed.add_field(
            name="💠 **Game Features**",
            value=(
                "> • Dynamic Esprit cards   \n"
                "> • Global economy & trading   \n"
                "> • Strategic, multi-unit battles   \n"
                "> • Rarity, team, synergy—your choices\n"
            ),
            inline=False
        )
        embed.add_field(
            name="🛠 **How to Use This Menu**",
            value=(
                "Choose a module below **or** tap a button for tips, stats, or support.\n"
                "Every command has a built-in `/help` for details."
            ),
            inline=False
        )
        embed.add_field(
            name="🌠 Wisdom of Faye",
            value=random.choice(FLAVOR_QUOTES),
            inline=False
        )
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(
            text="All progress is global • Need help? Tap Support • Menu closes in 5 minutes"
        )
        return embed

    async def show_home(self, interaction: discord.Interaction):
        embed = self.create_main_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_module(self, interaction: discord.Interaction, module_id: str):
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
        embed = discord.Embed(
            title="🚀 Quick Start Guide",
            description=(
                "**New to Faye? Follow these steps:**\n\n"
                "1️⃣ **`/start`** — Create your account & get your first Epic Esprit.\n"
                "2️⃣ **`/daily`** — Claim your daily bundle of Faylen, Virelite, and Ethryl.\n"
                "3️⃣ **`/summon`** — Use your starting Fayrites for your first summon!\n"
                "4️⃣ **`/inventory`** — Check all your new currencies.\n"
                "5️⃣ **`/esprit collection`** — View your growing collection.\n\n"
                "🎯 **Your Goal:** Collect rare Esprits, build your power, and explore the world!"
            ),
            color=0x2ECC71
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_support_info(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🆘 Get Support & Links",
            description=(
                "**Need help? We've got you covered:**\n\n"
                "🌐 **Website:** https://faye.bot\n"
                "💬 **Discord:** Join our support server for help & updates.\n"
                "📧 **Contact:** support@faye.bot\n\n"
                "Found a bug? Have a suggestion? Let us know in the support server!"
            ),
            color=0x3498DB
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_bot_stats(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Live Faye Statistics",
            description="Real-time bot performance and game stats:",
            color=0x9B59B6
        )
        embed.add_field(name="🌍 Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        # TODO: Wire up real stats later
        embed.add_field(name="👥 Players", value="Coming Soon", inline=True)
        embed.add_field(name="🔮 Esprits Summoned", value="Coming Soon", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

# --- Cog Definition ---

class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.modules = {
            "core": {
                "name": "🚀 Core Commands", "emoji": "🚀",
                "description": "The essential commands to start your journey.",
                "color": 0x2ECC71,
                "commands": [
                    {"cmd": "/start", "desc": "Begin your adventure and claim your first Epic Esprit."},
                    {"cmd": "/daily", "desc": "Claim your daily bundle of Faylen, Virelite, and Ethryl."},
                    {"cmd": "/inventory", "desc": "View all your currencies and materials."},
                ],
                "tips": [
                    "Your first Esprit is always **Epic** rarity!",
                    "Use `/inventory` to see your Fayrites, Faylen, and more.",
                ]
            },
            "summoning": {
                "name": "✨ Summoning", "emoji": "✨",
                "description": "Collect stunning Esprits via the summoning portal.",
                "color": 0xE91E63,
                "commands": [
                    {"cmd": "/summon", "desc": "Summon new Esprits using your Fayrites."},
                ],
                "tips": [
                    "**Fayrites** are the sole currency for standard summoning.",
                    "**Ethryl** is used for premium summons, which yield higher rarity Esprits.",
                    "Use `/inventory` to check your Fayrite balance before summoning.",
                    "Earn **Fayrite Shards** from gameplay to form new Fayrites.",
                ]
            },
            "esprit": {
                "name": "🔮 Esprit Management", "emoji": "🔮",
                "description": "Manage, view, and upgrade your powerful Esprits.",
                "color": 0x9B59B6,
                "commands": [
                    {"cmd": "/esprit collection", "desc": "Browse all the Esprits you've collected."},
                    {"cmd": "/esprit upgrade <id>", "desc": "Spend Virelite to level up an Esprit."},
                    {"cmd": "/esprit team view", "desc": "Set your active Esprit for your profile."},
                    {"cmd": "/esprit team set", "desc": "Arrange your 3-Esprit combat team."},
                    {"cmd": "/esprit team optimize", "desc": "Use AI-logic to equip your strongest esprits."},
                ],
                "tips": [
                    "Each Esprit has a unique ID, shown in its collection card.",
                    "Your Player Level determines the max level of your Esprits.",
                ]
            },
            "economy": {
                "name": "💰 Economy", "emoji": "💰",
                "description": "Understand Faye's multi-currency economic system.",
                "color": 0xFFC107,
                "commands": [
                    {"cmd": "/inventory", "desc": "The central hub for all your assets."},
                    {"cmd": "🔜 /marketplace", "desc": "Trade Esprits and items with other players."},
                ],
                "tips": [
                    "**<:faylen_icon:ID> Faylen:** Universal currency for shops and trading.",
                    "**<:fayrite_icon:ID> Fayrites:** The premium currency used for summoning.",
                    "**<:ethryl_icon:ID> Ethryl:** Used for premium summons and special features.",
                    "**<:virelite_icon:ID> Virelite:** Material used to level up your Esprits.",
                    "**<:remna_icon:ID> Remna:** Resources used for crafting and limit breaks.",
                ]
            },
             "progression": {
                "name": "⚔️ Progression", "emoji": "⚔️",
                "description": "Commands to track your growth and power.",
                "color": 0x3498DB,
                "commands": [
                    {"cmd": "🔜 /explore", "desc": "Embark on adventures to find rewards."},
                    {"cmd": "🔜 /tower", "desc": "Climb the tower to face powerful bosses."},
                    {"cmd": "🔜 /profile", "desc": "View your complete player profile and stats."},
                    {"cmd": "🔜 /level", "desc": "Check your current level and XP progress."},
                ],
                "tips": [
                    "**/explore** is the main way to earn **Fayrite Shards** and **Remna**.",
                    "Your Esprits can only be leveled as high as your player level allows.",
                ]
            },
        }

    @app_commands.command(name="help", description="Open the main Faye help center.")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = HelpView(self.modules, interaction.user.id, self.bot)
        embed = view.create_main_embed()
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
    logger.info("✅ HelpCog loaded")

