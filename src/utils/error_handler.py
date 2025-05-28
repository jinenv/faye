import discord
from discord.ext import commands
from src.utils.logger import Logger

log = Logger(__name__)

async def handle_command_error(ctx: commands.Context, error: commands.CommandError):
    """
    Centralized error handler for Discord commands.
    Provides user-friendly feedback and logs detailed errors.
    """
    # Determine the response method: followup for interactions, or regular send for prefix commands
    # We prioritize followup.send if an interaction is available and deferred/responded.
    send_method = None
    if ctx.interaction:
        # If interaction is already responded/deferred, use followup.send
        if ctx.interaction.response.is_done():
            send_method = ctx.interaction.followup.send
        else: # If interaction is not yet responded, use original interaction.response.send_message
            send_method = ctx.interaction.response.send_message
    else: # Fallback to ctx.send for non-interaction commands (like prefix commands)
        send_method = ctx.send

    # If the error is a check failure (e.g., cooldown, missing permissions)
    if isinstance(error, commands.CheckFailure):
        embed = discord.Embed(
            title="Access Denied 🚫",
            description=f"You do not have permission to use this command, or you are on cooldown. ({error})",
            color=discord.Color.red()
        )
        await send_method(embed=embed, ephemeral=True)
        log.warning(f"CheckFailure for user {ctx.author.id} on command {ctx.command}: {error}")
        return

    # If the command is not found
    if isinstance(error, commands.CommandNotFound):
        log.warning(f"CommandNotFound: {ctx.invoked_with}")
        return

    # If argument parsing failed
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="Missing Information 📝",
            description=f"You're missing a required piece of information for this command: `{error.param.name}`. Please check the command's usage.",
            color=discord.Color.gold()
        )
        if ctx.command:
            embed.set_footer(text=f"Usage: /{ctx.command.name} {ctx.command.signature}")
        await send_method(embed=embed, ephemeral=True)
        log.warning(f"MissingRequiredArgument for user {ctx.author.id} on command {ctx.command}: {error}")
        return

    # If bot is missing permissions
    if isinstance(error, commands.BotMissingPermissions):
        embed = discord.Embed(
            title="Bot Lacks Power! 🤖",
            description=f"I am missing the following permissions: {', '.join(error.missing_permissions)}. Please grant them!",
            color=discord.Color.red()
        )
        await send_method(embed=embed, ephemeral=False) # Make this public for server admins
        log.error(f"BotMissingPermissions for command {ctx.command}: {error}", exc_info=True)
        return

    # General unhandled exceptions in commands
    if isinstance(error, commands.CommandInvokeError):
        # The original exception is stored in error.original
        log.error(f"Error in command '{ctx.command.name}': {error.original}", exc_info=True)
        embed = discord.Embed(
            title="Cosmic Anomaly Detected 💥",
            description="An unexpected error occurred while executing that command. Nyxa's threads have tangled!\n"
                        "The celestial record has been updated. Please try again later.",
            color=discord.Color.dark_red()
        )
        await send_method(embed=embed, ephemeral=True)
        return

    # Any other unhandled error
    log.error(f"Unhandled command error: {error}", exc_info=True)
    embed = discord.Embed(
        title="Mysterious Forcefield 🛡️",
        description="An unknown error occurred. The weave of reality is unstable. Please inform the Creator.",
        color=discord.Color.dark_red()
    )
    await send_method(embed=embed, ephemeral=True)