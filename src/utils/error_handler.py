# src/utils/error_handler.py
import asyncio
import discord
from discord.ext import commands
import traceback
import logging

logger = logging.getLogger(__name__)

class ErrorHandler:
    """Centralized error handling for better user experience"""
    
    @staticmethod
    async def handle_interaction_error(interaction: discord.Interaction, error: Exception):
        """Handle errors in interactions gracefully"""
        
        # User-friendly error messages
        error_messages = {
            commands.CommandOnCooldown: "⏳ This command is on cooldown. Try again in {error.retry_after:.1f} seconds.",
            commands.MissingPermissions: "🚫 You don't have permission to use this command.",
            commands.BotMissingPermissions: "🤖 I don't have the necessary permissions to do this.",
            asyncio.TimeoutError: "⏱️ The operation timed out. Please try again.",
        }
        
        # Check for known error types
        for error_type, message in error_messages.items():
            if isinstance(error, error_type):
                embed = discord.Embed(
                    title="❌ Error",
                    description=message.format(error=error),
                    color=discord.Color.red()
                )
                break
        else:
            # Generic error message
            embed = discord.Embed(
                title="❌ An Error Occurred",
                description="Something went wrong while processing your request. The issue has been logged.",
                color=discord.Color.red()
            )
            
            # Log the full error
            logger.error(f"Unhandled error in {interaction.command.name if interaction.command else 'interaction'}: {error}")
            logger.error(traceback.format_exc())
        
        # Send error message
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")