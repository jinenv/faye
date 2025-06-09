# src/cogs/help_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List
from src.utils.logger import get_logger

logger = get_logger(__name__)

class HelpCog(commands.Cog):
    """Comprehensive help system with module selection."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Define all modules and their commands
        self.modules = {
            "🚀 Getting Started": {
                "description": "New to Nyxa? Start here!",
                "commands": [
                    {
                        "name": "/start",
                        "description": "Begin your adventure and get your first Epic Esprit + starting gold"
                    },
                    {
                        "name": "/balance", 
                        "description": "Check your current gold balance"
                    },
                    {
                        "name": "/inventory",
                        "description": "View your currencies and items (dust, fragments, chests)"
                    }
                ]
            },
            "✨ Summoning": {
                "description": "Collect powerful Esprits with beautiful art cards",
                "commands": [
                    {
                        "name": "/summon amount:[1 or 10]",
                        "description": "Summon 1 or 10 Esprits with dynamic art generation"
                    },
                    {
                        "name": "💡 Tip",
                        "description": "Single summons cost 100 gold, 10-pulls cost 1000 gold"
                    }
                ]
            },
            "🔮 Esprit Management": {
                "description": "View and manage your Esprit collection",
                "commands": [
                    {
                        "name": "/esprit collection",
                        "description": "Browse all your collected Esprits with pagination"
                    },
                    {
                        "name": "🔜 Combat System",
                        "description": "Battle system coming soon - use your Esprits in combat!"
                    }
                ]
            },
            "💰 Economy": {
                "description": "Earn and manage your in-game currencies",
                "commands": [
                    {
                        "name": "/daily",
                        "description": "Claim your daily gold reward (24-hour cooldown)"
                    },
                    {
                        "name": "/balance",
                        "description": "Check your current gold balance"
                    },
                    {
                        "name": "/inventory", 
                        "description": "View dust, fragments, and loot chests"
                    },
                    {
                        "name": "🔜 Marketplace",
                        "description": "Trade Esprits with other players (coming soon)"
                    }
                ]
            },
            "⚔️ Combat (Coming Soon)": {
                "description": "Battle system in development", 
                "commands": [
                    {
                        "name": "🚧 PvE Battles",
                        "description": "Fight AI opponents to earn rewards and level up Esprits"
                    },
                    {
                        "name": "🚧 PvP Arena", 
                        "description": "Challenge other players to Esprit battles"
                    },
                    {
                        "name": "🚧 Team Building",
                        "description": "Create strategic formations with multiple Esprits"
                    }
                ]
            },
            "🎮 Game Mechanics": {
                "description": "Understanding Nyxa's systems",
                "commands": [
                    {
                        "name": "🎯 Rarity System",
                        "description": "Common → Uncommon → Rare → Epic → Celestial → Supreme → Deity"
                    },
                    {
                        "name": "📊 Esprit Stats",
                        "description": "HP, Attack, Defense, Speed, Magic Resist, Crit Rate, and more"
                    },
                    {
                        "name": "💎 Currencies",
                        "description": "Gold (summoning), Dust (upgrades), Fragments (crafting)"
                    },
                    {
                        "name": "🌐 Cross-Server",
                        "description": "Your progress carries across all servers with Nyxa"
                    }
                ]
            },
            "🔗 Links & Support": {
                "description": "Get help and stay updated",
                "commands": [
                    {
                        "name": "🌐 Website",
                        "description": "https://nyxa.bot - Learn more about Nyxa"
                    },
                    {
                        "name": "💬 Support Server",
                        "description": "Join our Discord for help, updates, and community"
                    },
                    {
                        "name": "📧 Contact",
                        "description": "Report bugs or suggest features"
                    }
                ]
            }
        }

class ModuleDropdown(discord.ui.Select):
    def __init__(self, modules: Dict):
        self.modules = modules
        
        options = [
            discord.SelectOption(
                label=module_name,
                description=module_data["description"][:100],  # Discord limit
                emoji=module_name.split()[0]  # Extract emoji
            )
            for module_name, module_data in modules.items()
        ]
        
        super().__init__(
            placeholder="📚 Select a module to learn more...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_module = self.values[0]
        module_data = self.modules[selected_module]
        
        embed = discord.Embed(
            title=f"{selected_module}",
            description=module_data["description"],
            color=discord.Color.blurple()
        )
        
        for command in module_data["commands"]:
            embed.add_field(
                name=command["name"],
                value=command["description"],
                inline=False
            )
        
        embed.set_footer(text="Use the dropdown to explore other modules")
        
        # Update the message with the new embed
        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, modules: Dict, author_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.author_id = author_id
        self.add_item(ModuleDropdown(modules))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who used `/help` can interact with this menu.", 
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self):
        # Disable all components when the view times out
        for item in self.children:
            item.disabled = True

class HelpCog(commands.Cog):
    """Comprehensive help system with module selection."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Define all modules and their commands
        self.modules = {
            "🚀 Getting Started": {
                "description": "New to Nyxa? Start here!",
                "commands": [
                    {
                        "name": "/start",
                        "description": "Begin your adventure and get your first Epic Esprit + starting gold"
                    },
                    {
                        "name": "/balance", 
                        "description": "Check your current gold balance"
                    },
                    {
                        "name": "/inventory",
                        "description": "View your currencies and items (dust, fragments, chests)"
                    }
                ]
            },
            "✨ Summoning": {
                "description": "Collect powerful Esprits with beautiful art cards",
                "commands": [
                    {
                        "name": "/summon amount:[1 or 10]",
                        "description": "Summon 1 or 10 Esprits with dynamic art generation"
                    },
                    {
                        "name": "💡 Tip",
                        "description": "Single summons cost 100 gold, 10-pulls cost 1000 gold"
                    }
                ]
            },
            "🔮 Esprit Management": {
                "description": "View and manage your Esprit collection",
                "commands": [
                    {
                        "name": "/esprit collection",
                        "description": "Browse all your collected Esprits with pagination"
                    },
                    {
                        "name": "🔜 Combat System",
                        "description": "Battle system coming soon - use your Esprits in combat!"
                    }
                ]
            },
            "💰 Economy": {
                "description": "Earn and manage your in-game currencies",
                "commands": [
                    {
                        "name": "/daily",
                        "description": "Claim your daily gold reward (24-hour cooldown)"
                    },
                    {
                        "name": "/balance",
                        "description": "Check your current gold balance"
                    },
                    {
                        "name": "/inventory", 
                        "description": "View dust, fragments, and loot chests"
                    },
                    {
                        "name": "🔜 Marketplace",
                        "description": "Trade Esprits with other players (coming soon)"
                    }
                ]
            },
            "⚔️ Combat (Coming Soon)": {
                "description": "Battle system in development", 
                "commands": [
                    {
                        "name": "🚧 PvE Battles",
                        "description": "Fight AI opponents to earn rewards and level up Esprits"
                    },
                    {
                        "name": "🚧 PvP Arena", 
                        "description": "Challenge other players to Esprit battles"
                    },
                    {
                        "name": "🚧 Team Building",
                        "description": "Create strategic formations with multiple Esprits"
                    }
                ]
            },
            "🎮 Game Mechanics": {
                "description": "Understanding Nyxa's systems",
                "commands": [
                    {
                        "name": "🎯 Rarity System",
                        "description": "Common → Uncommon → Rare → Epic → Celestial → Supreme → Deity"
                    },
                    {
                        "name": "📊 Esprit Stats",
                        "description": "HP, Attack, Defense, Speed, Magic Resist, Crit Rate, and more"
                    },
                    {
                        "name": "💎 Currencies",
                        "description": "Gold (summoning), Dust (upgrades), Fragments (crafting)"
                    },
                    {
                        "name": "🌐 Cross-Server",
                        "description": "Your progress carries across all servers with Nyxa"
                    }
                ]
            },
            "🔗 Links & Support": {
                "description": "Get help and stay updated",
                "commands": [
                    {
                        "name": "🌐 Website",
                        "description": "https://nyxa.bot - Learn more about Nyxa"
                    },
                    {
                        "name": "💬 Support Server",
                        "description": "Join our Discord for help, updates, and community"
                    },
                    {
                        "name": "📧 Contact",
                        "description": "Report bugs or suggest features"
                    }
                ]
            }
        }
    
    @app_commands.command(name="help", description="Get help with Nyxa's features and commands")
    async def help_command(self, interaction: discord.Interaction):
        # Create the main help embed
        embed = discord.Embed(
            title="📚 Nyxa Help Center",
            description=(
                "Welcome to **Nyxa** - The Next Evolution of Discord Engagement!\n\n"
                "🔮 **Collect** stunning Esprits with dynamic art\n"
                "💰 **Build** your wealth in our global economy\n"
                "⚔️ **Battle** with your Esprits (coming soon)\n"
                "🌐 **Trade** with players across servers\n\n"
                "**Select a module below to get started!**"
            ),
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="🚀 Quick Start",
            value="New? Use `/start` to begin your adventure!",
            inline=False
        )
        
        embed.add_field(
            name="💡 Pro Tip",
            value="All your progress syncs across servers with Nyxa!",
            inline=False
        )
        
        embed.set_footer(text="Use the dropdown menu to explore different modules")
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        
        # Create the view with dropdown
        view = HelpView(self.modules, interaction.user.id)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
    logger.info("✅ HelpCog loaded")