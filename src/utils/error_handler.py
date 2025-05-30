# src/utils/error_handler.py
import discord
from discord.ext import commands

# Corrected import for the logger
from src.utils.logger import get_logger

log = get_logger(__name__) # Initialize logger with get_logger

async def handle_command_error(ctx: commands.Context, error: commands.CommandError):
    """
    Centralized error handling for all bot commands.
    """
    # If the error is a CheckFailure (e.g., missing permissions)
    if isinstance(error, commands.CheckFailure):
        await ctx.send(f"🚫 You don't have permission to use this command.", ephemeral=True)
        log.warning(f"Permission error: User {ctx.author} tried to use {ctx.command} but lacks permissions.")
    # If the command is on cooldown
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ This command is on cooldown. Try again in {error.retry_after:.2f} seconds.", ephemeral=True)
        log.info(f"Command cooldown: {ctx.command} used by {ctx.author} is on cooldown for {error.retry_after:.2f}s.")
    # If a required argument is missing
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: `{error.param.name}`. Please check the command usage.", ephemeral=True)
        log.warning(f"Missing argument for {ctx.command}: {error.param.name}")
    # If the command doesn't exist
    elif isinstance(error, commands.CommandNotFound):
        # We generally don't send a message for CommandNotFound to avoid spam
        # if users type random things. Log it for debugging.
        log.info(f"Command not found: '{ctx.message.content}' by {ctx.author}.")
    # Handling specific AppCommand errors for slash commands
    elif isinstance(error, discord.app_commands.AppCommandError):
        # For general AppCommand errors, you might want a more generic message
        await ctx.send(f"An application command error occurred: {error}", ephemeral=True)
        log.error(f"App command error in {ctx.command}: {error}", exc_info=True)
    # Generic error handler for any unhandled exception
    else:
        # Log the full traceback for unhandled errors
        log.error(f"Unhandled command error in {ctx.command}: {error}", exc_info=True)
        await ctx.send("An unexpected error occurred while processing your command. The developers have been notified.", ephemeral=True)